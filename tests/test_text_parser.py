"""Golden-file tests: real excerpts of each openfootball format under tests/fixtures/sources."""

from datetime import date, time, timedelta
from pathlib import Path

import pytest

from football_api.domain.enums import DecidedBy, MatchStatus, Side, Stage
from football_api.ingestion.openfootball.text_parser import (
    ParsedMatch,
    ParsedScore,
    normalize_stage,
    parse_file,
    parse_goals,
    parse_score,
)

SOURCES = Path(__file__).parent / "fixtures" / "sources"


def parse(path: str, start_year: int) -> list[ParsedMatch]:
    return parse_file(SOURCES / path, start_year=start_year, display_path=path)


def find(matches: list[ParsedMatch], home: str, away: str) -> ParsedMatch:
    return next(m for m in matches if m.home == home and m.away == away)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2-1 (1-0)", ParsedScore(2, 1, DecidedBy.REGULAR)),
        ("0-0", ParsedScore(0, 0, DecidedBy.REGULAR)),
        ("1-1 a.e.t. (1-1, 0-0)", ParsedScore(1, 1, DecidedBy.EXTRA_TIME)),
        ("3-3 a.e.t., 4-2 pen.", ParsedScore(3, 3, DecidedBy.PENALTIES, 4, 2)),
        ("5-3 pen. 1-1 a.e.t. (1-1, 0-1)", ParsedScore(1, 1, DecidedBy.PENALTIES, 5, 3)),
        ("4-3 pen. (1-1, 1-0)", ParsedScore(1, 1, DecidedBy.PENALTIES, 4, 3)),
        ("3-3 a.e.t. (2-2, 2-0), 4-2 pen.", ParsedScore(3, 3, DecidedBy.PENALTIES, 4, 2)),
    ],
)
def test_score_notations(text: str, expected: ParsedScore) -> None:
    assert parse_score(text) == expected


@pytest.mark.parametrize(
    ("label", "stage", "number"),
    [
        ("Matchday 7", Stage.LEAGUE, 7),
        ("League, Matchday 3", Stage.LEAGUE, 3),
        ("League phase", Stage.LEAGUE, None),
        ("Regular Season - 12", Stage.LEAGUE, 12),
        ("Round 3", Stage.ROUND, 3),
        ("2. Round", Stage.ROUND, 2),
        ("10. Runde", Stage.ROUND, 10),
        ("Preliminary round", Stage.PRELIMINARY, None),
        ("Round of 32", Stage.R32, None),
        ("Quarterfinals", Stage.QF, None),
        ("Playoffs, Matchday 1", Stage.PLAYOFF, 1),
        ("Group, Matchday 2", Stage.GROUP, 2),
        ("First stage / Group A", Stage.GROUP, None),
        ("Qualifying, Round 2", Stage.QUALIFYING, 2),
        ("Finals, Round of 16", Stage.R16, None),
        ("Quarter-final", Stage.QF, None),
        ("Finals, Semifinals", Stage.SF, None),
        ("Play-off for third place", Stage.THIRD_PLACE, None),
        ("Finals, Final", Stage.FINAL, None),
    ],
)
def test_normalize_stage(label: str, stage: Stage, number: int | None) -> None:
    assert normalize_stage(label) == (stage, number)


def test_league_file_carries_times_forward() -> None:
    matches = parse("england/2024-25/1-premierleague.txt", 2024)
    assert len(matches) == 20
    first = matches[0]
    assert (first.home, first.away, first.day, first.kickoff) == (
        "Manchester United FC",
        "Fulham FC",
        date(2024, 8, 16),
        time(20, 0),
    )
    # `           Everton FC v Brighton …` has no time of its own: it inherits 15:00.
    everton = find(matches, "Everton FC", "Brighton & Hove Albion FC")
    assert everton.kickoff == time(15, 0)
    assert everton.utc_offset is None
    assert all(not m.goals_listed for m in matches)


def test_awarded_match_keeps_its_score() -> None:
    matches = parse("deutschland/2024-25/1-bundesliga.txt", 2024)
    awarded = find(matches, "1. FC Union Berlin", "VfL Bochum 1848")
    assert awarded.status is MatchStatus.COMPLETED
    assert awarded.score == ParsedScore(0, 2, DecidedBy.REGULAR)


def test_postponed_match_and_two_legged_shootout() -> None:
    matches = parse("south-america/copa-libertadores/2025_copal.txt", 2025)
    postponed = find(matches, "CSD Colo-Colo (CHI)", "Fortaleza EC (BRA)")
    assert postponed.status is MatchStatus.POSTPONED
    assert postponed.score is None
    second_leg = find(matches, "São Paulo FC (BRA)", "CDC Atlético Nacional (COL)")
    assert second_leg.score == ParsedScore(1, 1, DecidedBy.PENALTIES, 4, 3)
    assert normalize_stage(second_leg.round_label) == (Stage.R16, None)


def test_world_cup_final() -> None:
    matches = parse("worldcup/more/2022.txt", 2022)
    final = find(matches, "Argentina", "France")
    assert final.day == date(2022, 12, 18)
    assert final.kickoff == time(18, 0)
    assert final.utc_offset == timedelta(hours=3)
    assert final.score == ParsedScore(3, 3, DecidedBy.PENALTIES, 4, 2)
    assert (final.venue_name, final.venue_city) == ("Lusail Stadium", "Al Daayen")
    goals = [(g.side, g.name, g.minute, g.is_penalty) for g in final.goals]
    assert goals == [
        (Side.HOME, "Lionel MESSI", 23, True),
        (Side.HOME, "Lionel MESSI", 108, False),
        (Side.HOME, "Angel DI MARIA", 36, False),
        (Side.AWAY, "Kylian MBAPPE", 80, True),
        (Side.AWAY, "Kylian MBAPPE", 81, False),
        (Side.AWAY, "Kylian MBAPPE", 118, True),
    ]


def test_goal_counts_match_scores_in_every_file() -> None:
    for path, year in [
        ("worldcup/more/2022.txt", 2022),
        ("euro/2024--germany/euro.txt", 2024),
        ("copa-america/2024--usa/copa.txt", 2024),
        ("club-worldcup/more/2025_clubworldcup-full.txt", 2025),
    ]:
        for m in parse(path, year):
            assert m.score is not None
            assert m.goals_listed or m.score.home + m.score.away == 0, (path, m.line_no)
            assert len(m.goals) == m.score.home + m.score.away, (path, m.line_no)


def test_added_time_minutes() -> None:
    matches = parse("worldcup/more/2022.txt", 2022)
    senegal_netherlands = find(matches, "Senegal", "Netherlands")
    klaassen = senegal_netherlands.goals[-1]
    assert (klaassen.name, klaassen.minute, klaassen.added_minute) == ("Davy KLAASSEN", 90, 9)


def test_euro_city_only_venue_uses_header_stadium_table() -> None:
    [final] = parse("euro/2024--germany/euro.txt", 2024)
    assert (final.venue_name, final.venue_city) == ("Olympiastadion", "Berlin")
    assert final.utc_offset is None  # file-level zone (Europe/Berlin) applies
    assert [(g.side, g.name) for g in final.goals] == [
        (Side.HOME, "Williams"),
        (Side.HOME, "Oyarzabal"),
        (Side.AWAY, "Palmer"),
    ]


def test_copa_inline_offsets_and_own_goal_flags() -> None:
    matches = parse("copa-america/2024--usa/copa.txt", 2024)
    assert all(m.utc_offset is not None for m in matches)
    assert all(m.day.year == 2024 for m in matches)
    opener = find(matches, "Argentina", "Canada")
    assert opener.utc_offset == timedelta(hours=-4)
    assert (opener.venue_name, opener.venue_city) == ("Mercedes-Benz Stadium", "Atlanta")
    assert [g.name for g in opener.goals] == ["Álvarez", "La. Martínez"]


def test_club_world_cup_full_file_skips_lineups() -> None:
    matches = parse("club-worldcup/more/2025_clubworldcup-full.txt", 2025)
    assert [(m.home, m.away) for m in matches] == [
        ("Al Ahly FC (EGY)", "Inter Miami CF (USA)"),
        ("Palmeiras (BRA)", "FC Porto (POR)"),
        ("Chelsea FC (ENG)", "Paris Saint-Germain (FRA)"),
    ]
    final = matches[-1]
    # Venue and offset come from the date line; the `Att:` part is not a city.
    assert (final.venue_name, final.venue_city) == ("Giants Stadium", "New York/New Jersey (East Rutherford)")
    assert final.utc_offset == timedelta(hours=-4)
    assert [(g.name, g.minute) for g in final.goals] == [("Cole PALMER", 22), ("Cole PALMER", 30), ("JOAO PEDRO", 43)]


def test_goal_block_without_semicolon_belongs_to_the_side_that_scored() -> None:
    goals = parse_goals("(Enner VALENCIA 16'(p), 31')", ParsedScore(0, 2, DecidedBy.REGULAR))
    assert [(g.side, g.name, g.minute, g.is_penalty) for g in goals] == [
        (Side.AWAY, "Enner VALENCIA", 16, True),
        (Side.AWAY, "Enner VALENCIA", 31, False),
    ]


def test_own_goal_flag() -> None:
    goals = parse_goals("(Palmer 13' (o.g.) Páez 45+4' (pen.); Antonio 54')", ParsedScore(2, 1, DecidedBy.REGULAR))
    assert [(g.name, g.is_own_goal, g.is_penalty, g.added_minute) for g in goals] == [
        ("Palmer", True, False, None),
        ("Páez", False, True, 4),
        ("Antonio", False, False, None),
    ]


def test_la_liga_2012_layout_with_dated_headings() -> None:
    """2012-13 to 2016-17: `HH:MM  Home  v Away  score (ht)` under `Sat Aug 18 2012` headings."""
    matches = parse("espana/2012-13/1-liga.txt", 2012)
    assert len(matches) == 20
    first = matches[0]
    assert (first.home, first.away, first.day, first.kickoff) == ("RC Celta", "Málaga CF", date(2012, 8, 18), time(19, 0))
    assert first.score == ParsedScore(0, 1, DecidedBy.REGULAR)
    last = matches[-1]
    assert (last.round_label, last.home, last.away, last.day) == ("Matchday 18", "Rayo Vallecano", "Getafe CF", date(2013, 1, 7))
    assert last.score == ParsedScore(3, 1, DecidedBy.REGULAR)


def test_la_liga_2020_layout_with_score_between_teams() -> None:
    """2020-21: `HH:MM  Home  score (ht)  Away`, year-less unindented dates, re-listed rescheduled matchdays."""
    matches = parse("espana/2020-21/1-liga.txt", 2020)
    assert len(matches) == 18
    eibar = find(matches, "SD Eibar", "RC Celta de Vigo")
    assert (eibar.day, eibar.kickoff, eibar.score) == (date(2020, 9, 12), time(16, 0), ParsedScore(0, 0, DecidedBy.REGULAR))
    no_time = find(matches, "SD Eibar", "Granada CF")  # time carried from the line above
    assert (no_time.day, no_time.kickoff, no_time.score) == (date(2021, 1, 3), time(18, 30), ParsedScore(2, 0, DecidedBy.REGULAR))
    rescheduled = find(matches, "Athletic Club", "FC Barcelona")
    assert (rescheduled.round_label, rescheduled.day) == ("Matchday 2", date(2021, 1, 6))
    assert rescheduled.score == ParsedScore(2, 3, DecidedBy.REGULAR)
