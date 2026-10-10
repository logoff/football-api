from dataclasses import replace
from pathlib import Path

from football_api.domain.enums import DecidedBy
from football_api.ingestion.openfootball.json_reader import is_current, read_json
from football_api.ingestion.openfootball.text_parser import ParsedScore, parse_file
from football_api.ingestion.seeds import load_competitions, load_teams

SOURCES = Path(__file__).parent / "fixtures" / "sources"


def test_real_seed_files_are_valid() -> None:
    competitions = load_competitions()
    teams = load_teams()  # also rejects duplicate aliases and QIDs
    assert len(competitions) == 13
    assert len({c.wikidata for c in competitions}) == 13
    assert all(t.wikidata for t in teams)
    assert all(c.season.tz for c in competitions)
    assert len(teams) > 250


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
