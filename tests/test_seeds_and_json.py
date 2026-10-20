import re
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from football_api.domain.enums import DecidedBy, TeamKind
from football_api.ingestion.openfootball.json_reader import is_current, read_json
from football_api.ingestion.openfootball.text_parser import ParsedScore, parse_file
from football_api.ingestion.seeds import CompetitionSeed, StandingsEra, load_competitions, load_standings, load_teams

SOURCES = Path(__file__).parent / "fixtures" / "sources"
SEEDS = Path(__file__).parent.parent / "seeds"
FIXTURE_SEEDS = Path(__file__).parent / "fixtures" / "seeds"


def test_real_seed_files_are_valid() -> None:
    competitions = load_competitions()
    teams = load_teams()  # also rejects duplicate aliases and QIDs
    assert len(competitions) == 19
    assert len({c.wikidata for c in competitions}) == 19
    # Only amateur cup clubs with no unambiguous Wikidata item go without a QID (add-domestic-cups D4).
    without_qid = [t for t in teams if not t.wikidata]
    assert all(t.kind is TeamKind.CLUB for t in without_qid) and len(without_qid) <= 64
    assert all(s.tz for c in competitions for s in c.seasons)
    assert len(teams) > 250
    assert not [t.name for t in teams if re.fullmatch(r"Q\d+", t.name)]  # a Wikidata ID is never a name


def test_real_events_seeds() -> None:
    """Every World Cup and Club World Cup, and the 2025-26 seasons of the five leagues (match-events)."""
    with_events = {(c.name, s.label): s for c in load_competitions() for s in c.seasons if s.events}
    assert len(with_events) == 49
    assert sum(name == "FIFA World Cup" for name, _ in with_events) == 23
    assert sum(name == "FIFA Club World Cup" for name, _ in with_events) == 21
    assert {name for name, label in with_events if label == "2025-26"} == {
        "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1",
    }
    assert all(s.events.endswith(("-full.txt", "_full.txt")) for s in with_events.values() if s.events)


def test_json_mirror_used_only_when_current() -> None:
    text = parse_file(SOURCES / "england/2024-25/1-premierleague.txt", start_year=2024, display_path="pl")
    mirror = read_json(SOURCES / "football.json/2024-25/en.1.json")
    assert is_current(mirror, text)
    assert [(m.home, m.away, m.score, m.day, m.kickoff) for m in mirror] == [
        (m.home, m.away, m.score, m.day, m.kickoff) for m in text
    ]


def test_json_mirror_missing_results_is_not_current() -> None:
    text = parse_file(SOURCES / "england/2024-25/1-premierleague.txt", start_year=2024, display_path="pl")
    mirror = read_json(SOURCES / "football.json/2024-25/en.1.json")
    stale = [replace(m, score=None) if i == 0 else m for i, m in enumerate(mirror)]
    assert not is_current(stale, text)
    assert not is_current(mirror[:-1], text)


def test_json_mirror_with_level_shootout_is_not_current() -> None:
    text = parse_file(SOURCES / "england/2024-25/1-premierleague.txt", start_year=2024, display_path="pl")
    mirror = read_json(SOURCES / "football.json/2024-25/en.1.json")
    broken = [replace(mirror[0], score=ParsedScore(0, 1, DecidedBy.PENALTIES, 4, 4)), *mirror[1:]]
    assert not is_current(broken, text)


def _competition(seasons: list[dict[str, object]]) -> dict[str, object]:
    return {"name": "X", "team_kind": "CLUB", "scope": "DOMESTIC", "format": "LEAGUE", "wikidata": "Q1", "seasons": seasons}


def _season(label: str) -> dict[str, object]:
    return {"label": label, "start_year": 2024, "file": f"x/{label}.txt", "tz": "UTC"}


def test_competition_needs_at_least_one_season() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        CompetitionSeed.model_validate(_competition([]))


def test_season_labels_are_unique_within_a_competition() -> None:
    with pytest.raises(ValidationError, match="duplicate season label"):
        CompetitionSeed.model_validate(_competition([_season("2024-25"), _season("2024-25")]))


def test_competition_with_several_seasons() -> None:
    seed = CompetitionSeed.model_validate(
        _competition([_season("2023-24"), {**_season("2024-25"), "wikipedia": "2024–25 X"}])
    )
    assert [s.label for s in seed.seasons] == ["2023-24", "2024-25"]
    assert [s.wikipedia for s in seed.seasons] == [None, "2024–25 X"]


def test_json_mirror_bare_full_time_pair(tmp_path: Path) -> None:
    """Recent mirrors sometimes write `"score": [0, 0]` instead of `{"ft": [0, 0]}`."""
    mirror = tmp_path / "es.1.json"
    mirror.write_text(
        '{"matches": [{"round": "Matchday 2", "date": "2026-08-22", "time": "19:30",'
        ' "team1": "Valencia CF", "team2": "RC Celta de Vigo", "score": [0, 0]}]}',
        encoding="utf-8",
    )
    [match] = read_json(mirror)
    assert match.score == ParsedScore(0, 0, DecidedBy.REGULAR)


@pytest.mark.parametrize("fmt", [None, "FRIENDLY"])
def test_competition_format_is_required_and_known(fmt: str | None) -> None:
    raw = _competition([_season("2024-25")])
    if fmt is None:
        del raw["format"]
    else:
        raw["format"] = fmt
    with pytest.raises(ValidationError, match="format"):
        CompetitionSeed.model_validate(raw)


def test_json_mirror_awarded_status(tmp_path: Path) -> None:
    mirror = tmp_path / "de.1.json"
    mirror.write_text(
        '{"matches": [{"round": "Matchday 14", "date": "2024-12-14", "team1": "1. FC Union Berlin",'
        ' "team2": "VfL Bochum 1848", "score": {"ft": [0, 2]}, "status": "awarded"}]}',
        encoding="utf-8",
    )
    [match] = read_json(mirror)
    assert (match.awarded, match.score) == (True, ParsedScore(0, 2, DecidedBy.REGULAR))


def test_json_mirror_that_lost_an_awarded_marker_is_not_current() -> None:
    text = parse_file(SOURCES / "deutschland/2024-25/1-bundesliga.txt", start_year=2024, display_path="bl")
    mirror = [replace(m, awarded=False) for m in text]
    assert is_current(text, text)
    assert not is_current(mirror, text)



def test_real_standings_seeds_are_valid() -> None:
    """Every league and tournament has ranking rules for each season, and standings.yaml loads."""
    competitions = load_competitions(SEEDS / "competitions.yaml")
    for comp in competitions:
        if comp.format.value in ("LEAGUE", "TOURNAMENT"):
            assert all(comp.era(s) is not None for s in comp.seasons), comp.name
    seeds = load_standings(SEEDS / "standings.yaml", competitions, load_teams(SEEDS / "teams.yaml"))
    assert seeds.adjustments and all(a.source.startswith("https://") for a in seeds.adjustments)


def _standings_file(tmp_path: Path, entry: str) -> Path:
    path = tmp_path / "standings.yaml"
    path.write_text(entry, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("entry", "error"),
    [
        ("competition: Q0\n    season: '2024-25'\n    team: Q9617", "no season"),
        ("competition: Q9448\n    season: '1900-01'\n    team: Q9617", "no season"),
        ("competition: Q9448\n    season: '2024-25'\n    team: Q0", "not in teams.yaml"),
    ],
)
def test_standings_entry_must_name_known_things(tmp_path: Path, entry: str, error: str) -> None:
    text = f"adjustments:\n  - {entry}\n    points: -1\n    reason: r\n    source: https://example.org\n"
    with pytest.raises(ValueError, match=error):
        load_standings(_standings_file(tmp_path, text), load_competitions(FIXTURE_SEEDS / "competitions.yaml"), load_teams(FIXTURE_SEEDS / "teams.yaml"))


def test_unknown_tie_breaker_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StandingsEra.model_validate({"from": 2000, "points": {"win": 3, "draw": 1}, "tiebreakers": ["coin_toss"]})


def test_eras_must_be_in_order() -> None:
    base = load_competitions(FIXTURE_SEEDS / "competitions.yaml")[0].model_dump(by_alias=True)
    base["standings"] = [
        {"from": 2000, "points": {"win": 3, "draw": 1}, "tiebreakers": []},
        {"from": 1990, "points": {"win": 2, "draw": 1}, "tiebreakers": []},
    ]
    with pytest.raises(ValidationError, match="increasing"):
        CompetitionSeed.model_validate(base)


def _teams_file(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "teams.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _team(name: str, qid: str, spellings: str, extra: str = "") -> str:
    return f"- name: {name}\n  kind: NATIONAL\n  country: null\n  wikidata: {qid}\n  openfootball:\n{spellings}{extra}"


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (
            _team("A", "Q1", "    - {name: X, until: 1992}\n") + _team("B", "Q2", "    - {name: X, from: 1990}\n"),
            "years overlap",
        ),
        (_team("A", "Q1", "    - X\n") + _team("B", "Q2", "    - {name: X, from: 1993}\n"), "both plain"),
        (_team("A", "Q1", "    - X\n", "  reference_wikidata: [Q2]\n") + _team("B", "Q2", "    - Y\n"), "own item"),
    ],
)
def test_team_spellings_and_reference_items_are_checked(tmp_path: Path, body: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        load_teams(_teams_file(tmp_path, body))


def test_year_scoped_spellings_that_meet_load() -> None:
    teams = {t.name: t for t in load_teams()}
    assert teams["Yugoslavia"].spelling_keys == ["Yugoslavia @-1992"]
    assert "Yugoslavia @1993-" in teams["Serbia and Montenegro"].spelling_keys
