import re
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from football_api.domain.enums import DecidedBy, TeamKind
from football_api.ingestion.openfootball.json_reader import is_current, read_json
from football_api.ingestion.openfootball.text_parser import ParsedScore, parse_file
from football_api.ingestion.seeds import CompetitionSeed, load_competitions, load_teams

SOURCES = Path(__file__).parent / "fixtures" / "sources"


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

