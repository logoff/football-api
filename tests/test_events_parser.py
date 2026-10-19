"""Lineups, substitutions, cards, referee and attendance from `-full` files (match-events)."""

import re
from pathlib import Path

import pytest

from football_api.domain.enums import CardKind, LineupRole
from football_api.ingestion.openfootball.events import (
    MatchEvents,
    ParsedCard,
    ParsedLineupEntry,
    ParsedSubstitution,
    SideEvents,
    parse_card_line,
    parse_events_file,
    parse_events_text,
    parse_lineup,
)
from football_api.ingestion.openfootball.text_parser import ParsedMatch, ParseError

SOURCES = Path(__file__).parent / "fixtures" / "sources"


def events_of(path: str, start_year: int, home: str, away: str) -> MatchEvents:
    parsed = parse_events_file(SOURCES / path, start_year=start_year, display_path=path)
    return next(e for m, e in parsed if (m.home, m.away) == (home, away))


def sides(events: MatchEvents) -> tuple[SideEvents, SideEvents]:
    assert events.home is not None and events.away is not None
    return events.home, events.away


def starters(side: SideEvents) -> list[tuple[str, int | None]]:
    return [(e.name, e.line_index) for e in side.entries if e.role is LineupRole.STARTER]


MATCH = """\
Sat Jun 14 20:00 UTC-4 @ Miami Stadium, Miami, Att: 60927
  Home FC (ENG) v Away FC (FRA)  1-0
     (A ONE 10')

Home FC: {home}
Away FC: K EEPER - B TWO, C THREE

Refs: Some REFEREE (AUS)
"""


def parse_one(home_lineup: str) -> tuple[ParsedMatch, MatchEvents]:
    [(match, events)] = parse_events_text(MATCH.format(home=home_lineup), start_year=2025, path="test.txt")
    return match, events


# --- 2.1 lineup blocks ----------------------------------------------------------------


def test_club_world_cup_final_inline_notation() -> None:
    events = events_of("club-worldcup/more/2025_clubworldcup-full.txt", 2025, "Chelsea FC (ENG)", "Paris Saint-Germain (FRA)")
    chelsea, psg = sides(events)
    assert events.attendance == 81118
    assert events.referee == "Alireza FAGHANI"
    assert [n for n, line in starters(chelsea) if line == 1] == ["Robert SANCHEZ"]
    assert [sum(1 for _, line in starters(chelsea) if line == i) for i in (2, 3, 4)] == [5, 3, 2]
    james = next(e for e in chelsea.entries if e.name == "Reece JAMES")
    assert (james.role, james.line_index, james.is_captain) == (LineupRole.STARTER, 2, True)
    assert [(s.minute, s.player_off, s.player_on) for s in chelsea.substitutions] == [
        (77, "Reece JAMES", "Kiernan DEWSBURY-HALL"),
        (61, "Enzo FERNANDEZ", "ANDREY SANTOS"),
        (77, "PEDRO NETO", "Christopher NKUNKU"),
        (67, "JOAO PEDRO", "Liam DELAP"),
    ]
    assert [e.name for e in chelsea.entries if e.role is LineupRole.SUBSTITUTE] == [
        "Kiernan DEWSBURY-HALL",
        "ANDREY SANTOS",
        "Christopher NKUNKU",
        "Liam DELAP",
    ]
    assert ParsedCard("JOAO NEVES", 85, None, CardKind.RED) in psg.cards
    assert ParsedCard("NUNO MENDES", 90, 4, CardKind.YELLOW) in psg.cards
    assert "Warren ZAIRE-EMERY" in [e.name for e in psg.entries]


def test_premier_league_card_lines() -> None:
    events = events_of("england/2025-26/1-premierleague-full.txt", 2025, "Burnley", "Liverpool")
    burnley, liverpool = sides(events)
    assert events.attendance == 21678
    assert events.referee == "Michael Oliver"
    assert burnley.cards == [
        ParsedCard("Lesley UGOCHUKWU", 16, None, CardKind.YELLOW),
        ParsedCard("Lesley UGOCHUKWU", 84, None, CardKind.SECOND_YELLOW),
    ]
    assert liverpool.cards == [
        ParsedCard("Milos KERKEZ", 22, None, CardKind.YELLOW),
        ParsedCard("Conor Bradley", 75, None, CardKind.YELLOW),
    ]
    assert len(starters(burnley)) == len(starters(liverpool)) == 11
    assert ParsedSubstitution(45, None, "Alexis MAC ALLISTER", "Conor Bradley") in liverpool.substitutions


def test_shootout_block_and_lineups_without_line_groups() -> None:
    events = events_of("club-worldcup/more/2018_clubworldcup-full.txt", 2018, "Al Ain (UAE)", "Team Wellington FC (NZL)")
    al_ain, wellington = sides(events)
    assert {line for _, line in starters(al_ain) + starters(wellington)} == {1}
    assert len(starters(al_ain)) == len(starters(wellington)) == 11
    assert al_ain.substitutions == al_ain.cards == wellington.substitutions == []
    assert (events.attendance, events.referee) == (15279, "Ryuji Sato")


def test_match_without_lineups() -> None:
    text = """\
Mon Feb 1 20:30 UTC+3 @ Ahmad Bin Ali Stadium, Ar-Rayyan
  Al Duhail (QAT) v Auckland City FC (NZL)  3-0


▪ 2nd Round
Thu Feb 4 17:00 UTC+3 @ Ahmad Bin Ali Stadium, Ar-Rayyan, Att: 866
  Tigres UANL (MEX) v Ulsan (KOR)  2-1
"""
    [(_, first), (_, second)] = parse_events_text(text, start_year=2021)
    assert first == MatchEvents()
    assert second == MatchEvents(attendance=866)


def test_lineup_must_head_the_match_line_spelling() -> None:
    with pytest.raises(ParseError, match=r"test.txt:5: lineup 'Other FC' doesn't head"):
        parse_events_text(MATCH.format(home="X").replace("Home FC: X", "Other FC: X"), start_year=2025, path="test.txt")


def test_only_one_lineup_fails() -> None:
    with pytest.raises(ParseError, match="only one lineup"):
        parse_events_text(MATCH.format(home="X").replace("Away FC: K EEPER - B TWO, C THREE\n", ""), start_year=2025)


# --- 2.2 lineup tokens ------------------------------------------------------------------


def test_chained_substitution() -> None:
    events = events_of("club-worldcup/more/2025_clubworldcup-full.txt", 2025, "Al Ahly FC (EGY)", "Inter Miami CF (USA)")
    al_ahly, _ = sides(events)
    assert ParsedSubstitution(14, None, "EMAM ASHOUR", "ZIZO") in al_ahly.substitutions
    assert ParsedSubstitution(79, None, "ZIZO", "MOHAMED AFSHA") in al_ahly.substitutions
    assert [e.name for e in al_ahly.entries if e.role is LineupRole.SUBSTITUTE].index("ZIZO") < [
        e.name for e in al_ahly.entries if e.role is LineupRole.SUBSTITUTE
    ].index("MOHAMED AFSHA")


def test_card_inside_a_substitution_bracket_belongs_to_the_substitute() -> None:
    events = events_of("club-worldcup/more/2025_clubworldcup-full.txt", 2025, "Palmeiras (BRA)", "FC Porto (POR)")
    _, porto = sides(events)
    assert ParsedCard("Nehuen PEREZ", 90, 1, CardKind.YELLOW) in porto.cards
    assert all(c.name != "JOAO MARIO" for c in porto.cards)


def test_captain_and_card_on_one_player() -> None:
    side = parse_lineup("Raul RANGEL - Cesar MONTES [c] [R 90+2'], Johan VASQUEZ")
    assert side.entries[1] == ParsedLineupEntry("Cesar MONTES", LineupRole.STARTER, 2, True)
    assert side.cards == [ParsedCard("Cesar MONTES", 90, 2, CardKind.RED)]


def test_second_yellow_inline() -> None:
    side = parse_lineup("Igor SMOLNIKOV [Y 28'] [Y/R 36']")
    assert [(c.minute, c.kind) for c in side.cards] == [(28, CardKind.YELLOW), (36, CardKind.SECOND_YELLOW)]


def test_unknown_tag_fails_with_file_and_line() -> None:
    with pytest.raises(ParseError, match=r"test.txt:5: unknown tag \[x 12'\]"):
        parse_one("K EEPER - A ONE [x 12'], B TWO")


# --- 2.3 card lines --------------------------------------------------------------------


def test_card_line_names_and_added_time() -> None:
    assert parse_card_line("Myles LEWIS-SKELLY 90+3', Danny WELBECK 90+11'", CardKind.YELLOW) == [
        ParsedCard("Myles LEWIS-SKELLY", 90, 3, CardKind.YELLOW),
        ParsedCard("Danny WELBECK", 90, 11, CardKind.YELLOW),
    ]


def test_card_line_without_minute_fails() -> None:
    text = MATCH.format(home="K EEPER - A ONE").replace("Away FC:", "    Red: A ONE\nAway FC:")
    with pytest.raises(ParseError, match=r":6: unrecognised card entry 'A ONE'"):
        parse_events_text(text, start_year=2025)


# --- 2.4 every events file in scope ----------------------------------------------------

REAL_SOURCES = Path(__file__).parent.parent / ".cache" / "sources"
EVENTS_FILES = sorted(
    [*REAL_SOURCES.glob("worldcup/more/*_full.txt"), *REAL_SOURCES.glob("club-worldcup/more/*_clubworldcup-full.txt")]
    + [*REAL_SOURCES.glob("*/2025-26/*-full.txt"), *REAL_SOURCES.glob("europe/france/2025-26_fr1-full.txt")]
)
# Sides whose source lineup doesn't list 11 starters: (file, home, away, side) → starters.
KNOWN_SHORT_LINEUPS = {
    ("worldcup/more/1954_full.txt", "Turkey", "South Korea", "away"): 10,
    ("club-worldcup/more/2020_clubworldcup-full.txt", "Palmeiras (BRA)", "Tigres UANL (MEX)", "home"): 10,
    ("club-worldcup/more/2020_clubworldcup-full.txt", "Al Ahly FC (EGY)", "Palmeiras (BRA)", "away"): 10,
    # `Callum HUDSON - ODOI`: spaces around the hyphen split one player into two line groups.
    ("club-worldcup/more/2021_clubworldcup-full.txt", "Chelsea (ENG)", "Palmeiras (BRA)", "home"): 12,
}
# Matches listed with a result and no lineups.
KNOWN_WITHOUT_LINEUPS = {("club-worldcup/more/2020_clubworldcup-full.txt", "Al Duhail (QAT)", "Auckland City FC (NZL)")}


def _source_counts(text: str) -> dict[CardKind, int]:
    """Card tags and card-line entries counted straight from the text, by kind."""
    tags = {
        kind: len(re.findall(rf"\[{tag} \d+(?:\+\d+)?'\]", text))
        for tag, kind in (("Y", CardKind.YELLOW), ("Y/R", CardKind.SECOND_YELLOW), ("R", CardKind.RED))
    }
    for label, kind in (("Yellow", CardKind.YELLOW), ("Yellow-Red", CardKind.SECOND_YELLOW), ("Red", CardKind.RED)):
        tags[kind] += sum(len(re.findall(r"\d+(?:\+\d+)?'", line)) for line in text.splitlines() if re.match(rf"^\s+{label}:", line))
    return tags


@pytest.mark.skipif(len(EVENTS_FILES) != 49, reason="needs the openfootball checkouts in .cache/sources (`just sync`)")
@pytest.mark.parametrize("path", EVENTS_FILES, ids=lambda p: str(p.relative_to(REAL_SOURCES)))
def test_every_events_file(path: Path) -> None:
    rel = str(path.relative_to(REAL_SOURCES))
    text = path.read_text(encoding="utf-8")
    start_year = re.search(r"\d{4}", rel)
    assert start_year
    parsed = parse_events_text(text, start_year=int(start_year.group(0)), path=rel)
    cards = {kind: 0 for kind in CardKind}
    captains = 0
    for match, events in parsed:
        if events.home is None or events.away is None:
            assert (rel, match.home, match.away) in KNOWN_WITHOUT_LINEUPS
            continue
        for name, side in (("home", events.home), ("away", events.away)):
            count = sum(e.role is LineupRole.STARTER for e in side.entries)
            assert count == KNOWN_SHORT_LINEUPS.get((rel, match.home, match.away, name), 11), (match.home, match.away, name)
            captains += sum(e.is_captain for e in side.entries)
            for card in side.cards:
                cards[card.kind] += 1
    assert cards == _source_counts(text)
    assert captains == text.count("[c]")
