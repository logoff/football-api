from datetime import date
from pathlib import Path

import pytest

from football_api.ingestion.openfootball.names import PersonName, fold, short_name_matches, split_capitalised
from football_api.ingestion.openfootball.squads import parse_more_squads, parse_per_team_squad

SOURCES = Path(__file__).parent / "fixtures" / "sources"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Lionel MESSI", PersonName("Lionel Messi", "Lionel", "Messi")),
        ("Mohamed Ali BEN ROMDHANE", PersonName("Mohamed Ali Ben Romdhane", "Mohamed Ali", "Ben Romdhane")),
        ("Kiernan DEWSBURY-HALL", PersonName("Kiernan Dewsbury-Hall", "Kiernan", "Dewsbury-Hall")),
        ("MARQUINHOS", PersonName("Marquinhos")),
        ("NUNO MENDES", PersonName("Nuno Mendes")),
    ],
)
def test_capitalised_surname_marks_the_split(raw: str, expected: PersonName) -> None:
    name = split_capitalised(raw)
    assert name == expected
    assert raw not in name.display or raw == name.display  # no stored capitals


def test_fold_ignores_case_and_accents() -> None:
    assert fold("Suárez") == fold("SUAREZ") == "suarez"


@pytest.mark.parametrize(
    ("short", "full", "expected"),
    [
        ("Koulibaly", "Kalidou Koulibaly", True),
        ("La. Martínez", "Lautaro Martínez", True),
        ("La. Martínez", "Lisandro Martínez", False),
        ("SUAREZ", "Luis Suárez", True),
        ("Di María", "Ángel Di María", True),
        ("Mendy", "Kalidou Koulibaly", False),
    ],
)
def test_short_name_matching(short: str, full: str, expected: bool) -> None:
    assert short_name_matches(short, full) is expected


def test_more_style_squads() -> None:
    players = parse_more_squads((SOURCES / "worldcup/more/2022_squads.txt").read_text(encoding="utf-8"))
    assert {p.team for p in players} == {
        "Argentina", "Croatia", "Ecuador", "France", "Morocco", "Netherlands", "Qatar", "Senegal",
    }
    messi = next(p for p in players if p.name.display == "Lionel Messi")
    assert (messi.team, messi.name.family, messi.position, messi.dob) == ("Argentina", "Messi", "FW", date(1987, 6, 24))


def test_per_team_squads_keep_names_unsplit() -> None:
    players = parse_per_team_squad((SOURCES / "euro/2024--germany/squads/spain.txt").read_text(encoding="utf-8"))
    assert {p.team for p in players} == {"Spain"}
    assert len(players) == 26
    raya = players[0]
    assert (raya.name, raya.shirt_number, raya.position, raya.birth_year) == (PersonName("David Raya"), 1, "GK", 1995)
