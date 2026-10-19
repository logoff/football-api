"""Lineups, substitutions, cards, referee and attendance from openfootball `-full` files.

A match's event block follows its goals (match-events design D4):

    Burnley: Martin DUBRAVKA - Maxime ESTEVE, …, Lesley UGOCHUKWU,
          Jaidon Anthony (89' Armando Broja) - …
        Yellow: Lesley UGOCHUKWU 16'
        Yellow-Red: Lesley UGOCHUKWU 84'

    Liverpool: ALISSON - Virgil VAN DIJK [c], Ibrahima KONATE (87' Jeremie FRIMPONG), …

    Refs: Michael Oliver, Stuart Burt, James Mainwaring

The home lineup comes first, headed by the home spelling of the match line without its
country code. Cards are tags on the player (`[Y 81']`, `[Y/R 78']`, `[R 85']`) or, in the
league files, card lines under the side's lineup. Anything not understood fails the file.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from football_api.domain.enums import CardKind, LineupRole
from football_api.ingestion.openfootball.text_parser import ParsedMatch, ParseError, is_date_line, parse_text

_COUNTRY_CODE_RE = re.compile(r"\s*\([A-Z]{3}\)$")
# An unindented `<Team>: …` line; date lines (`Sun Jul 13 15:00 …`) are told apart by is_date_line.
_HEADER_RE = re.compile(r"^(?P<name>[^\s#▪(][^:]*?):\s+(?P<rest>\S.*)$")
_NOT_LINEUPS = {"Refs", "Ref", "Penalties", "Att"}
_CARD_LINE_RE = re.compile(r"^\s+(?P<kind>Yellow|Yellow-Red|Red):\s*(?P<rest>.*)$")
_CARD_LINE_KINDS = {"Yellow": CardKind.YELLOW, "Yellow-Red": CardKind.SECOND_YELLOW, "Red": CardKind.RED}
_CARD_TAG_RE = re.compile(r"^(?P<kind>Y|Y/R|R)\s+(?P<min>\d+)(?:\+(?P<add>\d+))?'$")
_CARD_TAG_KINDS = {"Y": CardKind.YELLOW, "Y/R": CardKind.SECOND_YELLOW, "R": CardKind.RED}
_SUB_MINUTE_RE = re.compile(r"\(\s*(?P<min>\d+)(?:\+(?P<add>\d+))?'\s*")
_CARD_ENTRY_RE = re.compile(r"^(?P<name>.+?)\s+(?P<min>\d+)(?:\+(?P<add>\d+))?'$")
_ATTENDANCE_RE = re.compile(r"\bAtt:\s*(\d+)\b")
_REFS_RE = re.compile(r"^Refs?:\s*(?P<rest>.*)$")


@dataclass(frozen=True)
class ParsedLineupEntry:
    name: str
    role: LineupRole
    line_index: int | None  # 1-based source line group of a starter
    is_captain: bool


@dataclass(frozen=True)
class ParsedSubstitution:
    minute: int
    added_minute: int | None
    player_off: str
    player_on: str


@dataclass(frozen=True)
class ParsedCard:
    name: str
    minute: int
    added_minute: int | None
    kind: CardKind


@dataclass
class SideEvents:
    entries: list[ParsedLineupEntry] = field(default_factory=lambda: list[ParsedLineupEntry]())
    substitutions: list[ParsedSubstitution] = field(default_factory=lambda: list[ParsedSubstitution]())
    cards: list[ParsedCard] = field(default_factory=lambda: list[ParsedCard]())


@dataclass
class MatchEvents:
    home: SideEvents | None = None  # None: the source has no lineup block for the match
    away: SideEvents | None = None
    referee: str | None = None
    attendance: int | None = None


@dataclass
class _Player:
    name: str
    is_captain: bool = False
    cards: list[tuple[CardKind, int, int | None]] = field(default_factory=lambda: list[tuple[CardKind, int, int | None]]())
    # The substitution that took this player off: minute, added minute, the player who came on.
    sub: tuple[int, int | None, "_Player"] | None = None


class _LineupError(ValueError):
    pass


def _split_top_level(text: str, sep: str) -> list[str]:
    """Split on `sep` outside brackets: commas inside `(77' X, …)` chains belong to the chain."""
    parts: list[str] = []
    depth, start, i = 0, 0, 0
    while i < len(text):
        c = text[i]
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif depth == 0 and text.startswith(sep, i):
            parts.append(text[start:i])
            i += len(sep)
            start = i
            continue
        i += 1
    parts.append(text[start:])
    return [p.strip() for p in parts]


def _parse_player(text: str, pos: int) -> tuple[_Player, int]:
    """`NAME [c] [Y 12'] (60' NAME …)`, from `pos`; returns the player and the position after it."""
    end = pos
    while end < len(text) and text[end] not in "[()],":
        end += 1
    name = text[pos:end].strip()
    if not name:
        raise _LineupError(f"missing player name at {text[pos:pos + 30]!r}")
    player = _Player(name)
    pos = end
    while pos < len(text):
        while pos < len(text) and text[pos] == " ":
            pos += 1
        if pos >= len(text):
            break
        if text[pos] == "[":
            close = text.find("]", pos)
            if close < 0:
                raise _LineupError(f"unclosed tag at {text[pos:pos + 30]!r}")
            tag = text[pos + 1 : close].strip()
            if tag == "c":
                player.is_captain = True
            elif m := _CARD_TAG_RE.match(tag):
                player.cards.append((_CARD_TAG_KINDS[m["kind"]], int(m["min"]), int(m["add"]) if m["add"] else None))
            else:
                raise _LineupError(f"unknown tag [{tag}]")
            pos = close + 1
        elif text[pos] == "(" and player.sub is None:
            m = _SUB_MINUTE_RE.match(text, pos)
            if not m:
                raise _LineupError(f"substitution without a minute at {text[pos:pos + 30]!r}")
            on, pos = _parse_player(text, m.end())
            while pos < len(text) and text[pos] == " ":
                pos += 1
            if pos >= len(text) or text[pos] != ")":
                raise _LineupError(f"unclosed substitution at {text[m.start():m.start() + 40]!r}")
            player.sub = (int(m["min"]), int(m["add"]) if m["add"] else None, on)
            pos += 1
        else:
            break
    return player, pos


def parse_lineup(text: str) -> SideEvents:
    """One side's lineup (the text after `<Team>: `, continuation lines joined)."""
    side = SideEvents()
    starters: list[tuple[_Player, int]] = []
    for line_index, group in enumerate(_split_top_level(text, " - "), 1):
        for token in _split_top_level(group, ","):
            player, end = _parse_player(token, 0)
            if end != len(token):
                raise _LineupError(f"unexpected text {token[end:]!r} after {player.name!r}")
            starters.append((player, line_index))

    substitutes: list[_Player] = []
    for player, line_index in starters:
        side.entries.append(ParsedLineupEntry(player.name, LineupRole.STARTER, line_index, player.is_captain))
        current = player
        while True:
            side.cards += [ParsedCard(current.name, minute, added, kind) for kind, minute, added in current.cards]
            if current.sub is None:
                break
            minute, added, on = current.sub
            side.substitutions.append(ParsedSubstitution(minute, added, current.name, on.name))
            substitutes.append(on)
            current = on
    side.entries += [ParsedLineupEntry(p.name, LineupRole.SUBSTITUTE, None, p.is_captain) for p in substitutes]
    return side


def parse_card_line(text: str, kind: CardKind) -> list[ParsedCard]:
    """`Milos KERKEZ 43', Conor Bradley 75'` → cards of one kind."""
    cards: list[ParsedCard] = []
    for item in _split_top_level(text, ","):
        m = _CARD_ENTRY_RE.match(item)
        if not m:
            raise _LineupError(f"unrecognised card entry {item!r}")
        cards.append(ParsedCard(m["name"], int(m["min"]), int(m["add"]) if m["add"] else None, kind))
    return cards


def _referee(text: str) -> str | None:
    first = _split_top_level(text, ",")[0]
    name = _COUNTRY_CODE_RE.sub("", first).strip()
    return name or None


def team_header(spelling: str) -> str:
    """The name a lineup is headed by: the match-line spelling without its country code."""
    return _COUNTRY_CODE_RE.sub("", spelling).strip()


def _lineup_header(raw: str) -> re.Match[str] | None:
    if raw[:1].isspace():
        return None
    m = _HEADER_RE.match(raw.rstrip())
    if not m or m["name"] in _NOT_LINEUPS or is_date_line(raw):
        return None
    return m


def _read_block(lines: list[str], start: int, end: int, match: ParsedMatch, path: str) -> MatchEvents:
    """The event block of `match` in `lines[start:end]` (0-based, after the match line)."""
    events = MatchEvents()
    expected = [team_header(match.home), team_header(match.away)]
    sides: list[SideEvents] = []
    card_lines: list[dict[CardKind, list[ParsedCard]]] = []
    lineup_text: list[str] | None = None
    lineup_line = 0

    def close_lineup() -> None:
        nonlocal lineup_text
        if lineup_text is None:
            return
        try:
            sides.append(parse_lineup(" ".join(lineup_text)))
        except _LineupError as exc:
            raise ParseError(path, lineup_line, str(exc)) from exc
        lineup_text = None

    for idx in range(start, end):
        raw = lines[idx]
        line_no = idx + 1
        stripped = raw.strip()
        if lineup_text is not None and raw[:1].isspace() and stripped and not _CARD_LINE_RE.match(raw):
            lineup_text.append(stripped)
            continue
        close_lineup()
        if not stripped:
            continue
        if card := _CARD_LINE_RE.match(raw):
            if not sides:
                raise ParseError(path, line_no, "card line before any lineup")
            try:
                card_lines[-1].setdefault(_CARD_LINE_KINDS[card["kind"]], []).extend(
                    parse_card_line(card["rest"], _CARD_LINE_KINDS[card["kind"]])
                )
            except _LineupError as exc:
                raise ParseError(path, line_no, str(exc)) from exc
            continue
        if refs := _REFS_RE.match(stripped):
            if sides:
                events.referee = _referee(refs["rest"])
                break
            continue
        header = _lineup_header(raw)
        if header is None:
            if len(sides) == 2:
                break  # the next match's header; this one had no `Refs:` line
            continue
        if len(sides) == 2:
            break
        if header["name"] != expected[len(sides)]:
            if not sides:
                raise ParseError(path, line_no, f"lineup {header['name']!r} doesn't head {expected[0]!r} v {expected[1]!r}")
            raise ParseError(path, line_no, f"expected the {expected[1]!r} lineup, found {header['name']!r}")
        lineup_text, lineup_line = [header["rest"]], line_no
        card_lines.append({})
    close_lineup()

    if len(sides) == 1:
        raise ParseError(path, match.line_no, f"only one lineup for {match.home} v {match.away}")
    for side, by_kind in zip(sides, card_lines, strict=True):
        for kind in (CardKind.YELLOW, CardKind.SECOND_YELLOW, CardKind.RED):
            side.cards += by_kind.get(kind, [])
    if sides:
        events.home, events.away = sides
    return events


def parse_events_text(text: str, *, start_year: int, path: str = "<text>") -> list[tuple[ParsedMatch, MatchEvents]]:
    """Every match of a `-full` file with its events (empty `MatchEvents` when it has none)."""
    lines = text.splitlines()
    matches = parse_text(text, start_year=start_year, path=path)
    out: list[tuple[ParsedMatch, MatchEvents]] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].line_no - 1 if i + 1 < len(matches) else len(lines)
        events = _read_block(lines, match.line_no, end, match, path)
        for header_line in (lines[match.line_no - 1], lines[match.line_no - 2] if match.line_no >= 2 else ""):
            if m := _ATTENDANCE_RE.search(header_line):
                events.attendance = int(m.group(1))
                break
        out.append((match, events))
    return out


def parse_events_file(path: Path, *, start_year: int, display_path: str) -> list[tuple[ParsedMatch, MatchEvents]]:
    return parse_events_text(path.read_text(encoding="utf-8"), start_year=start_year, path=display_path)
