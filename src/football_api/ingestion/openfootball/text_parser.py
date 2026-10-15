"""Parser for the openfootball text format (league, tournament and `more/` styles).

The format is a loose line-oriented DSL. Lines are classified as round headers
(`▪ Matchday 1`), date markers (`Sat Aug 17 [2024] [20:00 [UTC-4]] …`), time-prefixed
match lines, goal blocks (`(Name 12', …; Name 80')`) and everything else, which is
ignored (comments, group tables, lineups in `-full` files).
"""

import re
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from pathlib import Path

from football_api.domain.enums import DecidedBy, MatchStatus, Side, Stage

MONTHS = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}

# `Fri Aug 15`, `Aug 15 2025`, `June 14`: weekday optional, month name short or full.
_DATE_RE = re.compile(
    r"^\s*(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+)?"
    r"(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?:uary|ruary|ch|il|e|y|ust|tember|ober|ember)?"
    r"\s+(?P<day>\d{1,2})(?:\s+(?P<year>\d{4}))?\b(?P<rest>.*)$"
)
# `20:45`, `18:00 UTC-3`, or `15:00 (17:00 UTC+4)` where the bracketed local time carries the offset.
_TIME_RE = re.compile(
    r"^\s*(?P<h>\d{1,2}):(?P<m>\d{2})\b(?:\s+UTC(?P<off>[+-]\d{1,2})\b)?"
    r"(?:\s+\((?P<lh>\d{1,2}):(?P<lm>\d{2})\s+UTC(?P<loff>[+-]\d{1,2})\))?"
    r"(?:\s+\(\d{1,2}:\d{2}\s+[A-Z]{2,5}\))?"  # `18:00 (19:00 EEST)`: a note; the first time is in the file's zone
    r"(?P<rest>.*)$"
)
_TRAILING_SHOOTOUT_RE = re.compile(r"\s*\(\s*\d+-\d+\s*pen\.?\s*\)\s*$")
# `England 2-2 Portugal (aet, 6-5 pen)`, `(aet/gg)`, `(aet/sg)`: golden and silver goals were extra time.
_TRAILING_AET_RE = re.compile(r"\s*\(\s*aet(?:/[gs]g)?(?:\s*,\s*(?P<pens>\d+-\d+)\s*pen\.?)?\s*\)\s*$", re.I)
_PLACEHOLDER_TEAMS = {"N.N.", "N.N"}  # a fixture whose teams aren't known yet
_PENALTIES_RE = re.compile(r"^penalties\s*:", re.I)
_LEADING_VENUE_RE = re.compile(r"^\s*@\s*(?P<venue>.+?)\s{2,}(?P<rest>\S.*)$")
_SCORE_TOKEN_RE = re.compile(r"\s*(\d+-\d+|a\.e\.t\.?,?|pen\.?,?|\([^)]*\),?|,)")
_FIRST_SCORE_RE = re.compile(r"(?:^|\s)(\d+-\d+)(?=\s|,|$)")
_V_SPLIT_RE = re.compile(r"\s+v\s+")
_STADIUM_RE = re.compile(r"^#\s+(?P<city>[^,]+),\s+(?P<name>[^,(]+?)\s*(?:\([^)]*\))?\s*,")
_GOAL_RE = re.compile(
    r"(?P<name>[^\d,;()']+?)?\s*(?P<min>\d+)(?:\+(?P<add>\d+))?'\s*(?P<flags>(?:\(\s*(?:p|pen\.?|og|o\.g\.)\s*\)\s*)*)"
)


class ParseError(Exception):
    def __init__(self, path: str, line_no: int, message: str) -> None:
        super().__init__(f"{path}:{line_no}: {message}")
        self.path = path
        self.line_no = line_no


@dataclass(frozen=True)
class ParsedScore:
    home: int
    away: int
    decided_by: DecidedBy
    home_pens: int | None = None
    away_pens: int | None = None


@dataclass(frozen=True)
class ParsedGoal:
    side: Side
    name: str
    minute: int
    added_minute: int | None
    is_penalty: bool
    is_own_goal: bool


@dataclass
class ParsedMatch:
    line_no: int
    round_label: str
    day: date
    kickoff: time | None
    utc_offset: timedelta | None
    home: str
    away: str
    score: ParsedScore | None
    venue_name: str | None = None
    venue_city: str | None = None
    goals: list[ParsedGoal] = field(default_factory=lambda: list[ParsedGoal]())
    goals_listed: bool = False
    status: MatchStatus = MatchStatus.COMPLETED
    awarded: bool = False  # decided off the pitch; the score is whatever the source records


def parse_score(text: str) -> ParsedScore:
    """Parse every score notation observed in the in-scope files.

    `2-1 (1-0)` · `1-1 a.e.t. (1-1, 0-0)` · `3-3 a.e.t., 4-2 pen.` ·
    `5-3 pen. 1-1 a.e.t. (1-1, 0-1)` · `4-3 pen. (1-1, 1-0)` · `3-3 a.e.t. (2-2, 2-0), 4-2 pen.`
    """
    pens = re.search(r"(\d+)-(\d+)\s*pen\.?", text)
    aet = re.search(r"(\d+)-(\d+)\s*a\.e\.t\.?", text)
    rest = text
    for m in (pens, aet):
        if m:
            rest = rest.replace(m.group(0), " ")
    bare = re.search(r"(\d+)-(\d+)", re.sub(r"\([^)]*\)", " ", rest))
    paren = re.search(r"\((\d+)-(\d+)", rest)

    if aet:
        home, away = int(aet.group(1)), int(aet.group(2))
    elif bare:
        home, away = int(bare.group(1)), int(bare.group(2))
    elif pens and paren:  # `4-3 pen. (1-1, 1-0)`: regular-time score is in the brackets
        home, away = int(paren.group(1)), int(paren.group(2))
    else:
        raise ValueError(f"unrecognised score: {text!r}")

    if pens:
        return ParsedScore(home, away, DecidedBy.PENALTIES, int(pens.group(1)), int(pens.group(2)))
    return ParsedScore(home, away, DecidedBy.EXTRA_TIME if aet else DecidedBy.REGULAR)


def _split_score(text: str) -> tuple[str, str, str] | None:
    """Split `Home <score> Away` into its parts; None when no score is present."""
    first = _FIRST_SCORE_RE.search(text)
    if not first:
        return None
    start = first.start(1)
    pos = start
    while m := _SCORE_TOKEN_RE.match(text, pos):
        if m.end() == pos:
            break
        pos = m.end()
    return text[:start].strip(), text[start:pos].strip(), text[pos:].strip()


def _parse_teams_and_score(text: str) -> tuple[str, str, ParsedScore | None] | None:
    if _V_SPLIT_RE.search(text):
        home, rest = _V_SPLIT_RE.split(text, maxsplit=1)
        parts = _split_score(rest)
        if parts is None:
            return home.strip(), rest.strip(), None
        away, score, trailing = parts
        if trailing:
            return None
        return home.strip(), away, parse_score(score)
    parts = _split_score(text)
    if parts is None:
        return None
    home, score, away = parts
    if shootout := _TRAILING_SHOOTOUT_RE.search(away):  # `Czechoslovakia 1-1 Italy (9-8 pen)`
        away, score = away[: shootout.start()].strip(), f"{score} {shootout.group(0).strip()}"
    elif extra := _TRAILING_AET_RE.search(away):
        pens = f", {extra.group('pens')} pen." if extra.group("pens") else ""
        away, score = away[: extra.start()].strip(), f"{score} a.e.t.{pens}"
    if not home or not away:
        return None
    return home, away, parse_score(score)


def _strip_comment(line: str) -> str:
    idx = line.find(" #")
    return line[:idx] if idx >= 0 else line


_TAG_RE = re.compile(r"\s*\[(?P<tag>[a-z ]+)\]\s*$")
_TAG_STATUS = {
    "awarded": MatchStatus.COMPLETED,
    "postponed": MatchStatus.POSTPONED,
    "cancelled": MatchStatus.CANCELLED,
    "canceled": MatchStatus.CANCELLED,
}


def _split_venue(text: str) -> tuple[str, str | None]:
    if text.startswith("@"):
        return "", text[1:].strip()
    idx = text.find(" @ ")
    if idx < 0:
        return text, None
    return text[:idx], text[idx + 3 :].strip()


def parse_goals(block: str, score: ParsedScore | None) -> list[ParsedGoal]:
    """Parse `(A 12', 30'(p); B 80'(og))`. Goals before `;` are home, after are away.

    With no `;`, every goal belongs to the side that scored. Own goals are listed
    under the side that benefited, which is the side they count for.
    """
    inner = block.strip()
    if inner.startswith("("):
        inner = inner[1:]
    if inner.endswith(")"):
        inner = inner[:-1]
    if ";" in inner:
        home_text, away_text = inner.split(";", 1)
        sides = [(Side.HOME, home_text), (Side.AWAY, away_text)]
    elif score is not None and score.home == 0:
        sides = [(Side.AWAY, inner)]
    else:
        sides = [(Side.HOME, inner)]

    goals: list[ParsedGoal] = []
    for side, text in sides:
        name = ""
        for m in _GOAL_RE.finditer(text):
            raw_name = (m.group("name") or "").strip(" ,")
            if raw_name:
                name = raw_name
            if not name:
                continue
            flags = m.group("flags").replace(" ", "")
            goals.append(
                ParsedGoal(
                    side=side,
                    name=name,
                    minute=int(m.group("min")),
                    added_minute=int(m.group("add")) if m.group("add") else None,
                    is_penalty="(p" in flags,
                    is_own_goal="(o" in flags,
                )
            )
    return goals


@dataclass
class _State:
    year: int
    month: int = 0
    day: date | None = None
    kickoff: time | None = None
    offset: timedelta | None = None
    pending_venue: str | None = None
    rounds: list[str] = field(default_factory=lambda: list[str]())


def parse_text(text: str, *, start_year: int, path: str = "<text>") -> list[ParsedMatch]:
    """Parse a whole openfootball text file into matches (with goals when listed)."""
    lines = text.splitlines()
    stadiums: dict[str, str] = {}
    in_stadiums = False
    for raw in lines:
        if raw.strip().lower().startswith("# stadiums"):
            in_stadiums = True
            continue
        if in_stadiums:
            m = _STADIUM_RE.match(raw.strip())
            if m:
                stadiums[m.group("city").strip()] = m.group("name").strip()
            elif raw.strip() and not raw.strip().startswith("#"):
                in_stadiums = False

    state = _State(year=start_year)
    matches: list[ParsedMatch] = []
    goal_buf: list[str] | None = None
    goal_target: ParsedMatch | None = None

    def flush_goals() -> None:
        nonlocal goal_buf, goal_target
        if goal_buf is not None and goal_target is not None:
            goal_target.goals = parse_goals(" ".join(goal_buf), goal_target.score)
            goal_target.goals_listed = True
        goal_buf, goal_target = None, None

    in_shootout = False  # inside a `Penalties: 1-0 Masny, 1-1 Bonhof, …` kick-by-kick block
    for line_no, raw in enumerate(lines, 1):
        stripped = raw.strip()

        if _PENALTIES_RE.match(stripped):
            in_shootout = True
            continue
        if in_shootout:
            if stripped and ":" not in stripped and not stripped.startswith(("▪", "#")):
                continue
            in_shootout = False

        if goal_buf is not None:
            goal_buf.append(stripped)
            if " ".join(goal_buf).count("(") <= " ".join(goal_buf).count(")"):
                flush_goals()
            continue

        if not stripped or stripped.startswith("#") or stripped.startswith("=") or "|" in stripped:
            continue

        if stripped.startswith("▪"):
            level = len(stripped) - len(stripped.lstrip("▪"))
            label = stripped.lstrip("▪").strip()
            state.rounds = state.rounds[: level - 1] + [label]
            continue

        if stripped.startswith("(") and matches and matches[-1].line_no >= line_no - 3:
            goal_buf, goal_target = [stripped], matches[-1]
            if stripped.count("(") <= stripped.count(")"):
                flush_goals()
            continue

        body = _strip_comment(raw)
        date_match = _DATE_RE.match(body)
        if date_match:
            month = MONTHS[date_match.group("mon")]
            if date_match.group("year"):
                state.year = int(date_match.group("year"))
            elif state.month and month < state.month - 6:
                state.year += 1
            state.month = month
            state.day = date(state.year, month, int(date_match.group("day")))
            state.kickoff, state.offset, state.pending_venue = None, None, None
            body = date_match.group("rest")
            if not body.strip():
                continue

        time_match = _TIME_RE.match(body)
        if time_match:
            if time_match.group("lh"):  # a local time with its own offset wins over the file's zone
                state.kickoff = time(int(time_match.group("lh")), int(time_match.group("lm")))
                state.offset = timedelta(hours=int(time_match.group("loff")))
            else:
                state.kickoff = time(int(time_match.group("h")), int(time_match.group("m")))
                off = time_match.group("off")
                state.offset = timedelta(hours=int(off)) if off else None
            body = time_match.group("rest")

        leading_venue = _LEADING_VENUE_RE.match(body)
        if leading_venue and _FIRST_SCORE_RE.search(leading_venue.group("rest")):
            # `June 10 @ Düsseldorf     West Germany  1-1 Italy`: the venue precedes the match
            state.pending_venue = leading_venue.group("venue").strip()
            body = leading_venue.group("rest")

        tag = _TAG_RE.search(body)
        status: MatchStatus | None = None
        awarded = False
        if tag and tag.group("tag").strip() in _TAG_STATUS:
            status = _TAG_STATUS[tag.group("tag").strip()]
            awarded = tag.group("tag").strip() == "awarded"
            body = body[: tag.start()]

        content, venue = _split_venue(body.strip())
        if not content:
            state.pending_venue = venue
            continue
        if ":" in content.split(" v ")[0] and not _FIRST_SCORE_RE.search(content):
            continue  # lineup / referee lines in `-full` files

        parsed = _parse_teams_and_score(content)
        if parsed is None:
            continue
        if state.day is None:
            raise ParseError(path, line_no, "match line before any date marker")

        venue = venue or state.pending_venue
        state.pending_venue = None
        venue_name, venue_city = _split_venue_text(venue, stadiums)
        home, away, score = parsed
        if home in _PLACEHOLDER_TEAMS or away in _PLACEHOLDER_TEAMS:
            continue
        if status is None:
            status = MatchStatus.COMPLETED if score else MatchStatus.SCHEDULED
        matches.append(
            ParsedMatch(
                line_no=line_no,
                round_label=" / ".join(state.rounds),
                day=state.day,
                kickoff=state.kickoff,
                utc_offset=state.offset,
                home=home,
                away=away,
                score=score,
                venue_name=venue_name,
                venue_city=venue_city,
                status=status,
                awarded=awarded,
            )
        )

    flush_goals()
    return matches


def _split_venue_text(venue: str | None, stadiums: dict[str, str]) -> tuple[str | None, str | None]:
    if not venue:
        return None, None
    parts = [p.strip() for p in venue.split(",") if p.strip() and not p.strip().startswith("Att:")]
    if len(parts) == 1:
        # `@ Berlin` — the file names only the city; the stadium comes from its header table.
        city = parts[0]
        return stadiums.get(city), city
    return parts[0], parts[1]


def parse_file(path: Path, *, start_year: int, display_path: str) -> list[ParsedMatch]:
    return parse_text(path.read_text(encoding="utf-8"), start_year=start_year, path=display_path)


_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}

_STAGE_RULES: list[tuple[re.Pattern[str], Stage]] = [
    (re.compile(r"qualif", re.I), Stage.QUALIFYING),
    (re.compile(r"third place|3rd place", re.I), Stage.THIRD_PLACE),
    (re.compile(r"fifth place|5th place", re.I), Stage.FIFTH_PLACE),
    # German knockout labels in some UEFA files: Sechzehntel-/Achtel-/Viertel-/Halbfinale.
    (re.compile(r"sechzehntelfinale", re.I), Stage.R32),
    (re.compile(r"achtelfinale", re.I), Stage.R16),
    (re.compile(r"viertelfinale", re.I), Stage.QF),
    (re.compile(r"halbfinale", re.I), Stage.SF),
    (re.compile(r"semi", re.I), Stage.SF),
    (re.compile(r"quarter", re.I), Stage.QF),
    (re.compile(r"round of 16", re.I), Stage.R16),
    (re.compile(r"round of 32", re.I), Stage.R32),
    (re.compile(r"\bfinal\b", re.I), Stage.FINAL),
    (re.compile(r"play-?offs?", re.I), Stage.PLAYOFF),
    (re.compile(r"group|gruppe", re.I), Stage.GROUP),
    (re.compile(r"league|matchday|regular season", re.I), Stage.LEAGUE),
    (re.compile(r"prelim", re.I), Stage.PRELIMINARY),
    # Numbered cup rounds, after the named ones so `Round of 16` stays R16:
    # `Round 3`, `2. Round`, `10. Runde`, `1st Round`, `First round`.
    (re.compile(r"^(?:(?:round|runde)\s*\d+|\d+\.\s*(?:round|runde)|(?:\d+(?:st|nd|rd|th)|" + "|".join(_ORDINALS) + r")\s+round)$", re.I), Stage.ROUND),
]


def normalize_stage(round_label: str) -> tuple[Stage, int | None]:
    """Map a source round label to a stage code plus an optional matchday/round number.

    Rules are tried in priority order against the whole label, so the most specific
    one wins (`Finals, Semifinals` → `SF`, `Playoffs, Matchday 1` → `PLAYOFF`).
    """
    number = re.search(
        r"(?:matchday|round|runde|regular season\s*-)\s*(\d+)\s*$|^(\d+)(?:\.|st|nd|rd|th)\s*(?:round|runde)$", round_label, re.I
    )
    ordinal = re.match(r"^(" + "|".join(_ORDINALS) + r")\s+round$", round_label, re.I)
    for pattern, code in _STAGE_RULES:
        if pattern.search(round_label):
            if ordinal:
                return code, _ORDINALS[ordinal.group(1).lower()]
            return code, int(number.group(1) or number.group(2)) if number else None
    raise ValueError(f"unrecognised round label: {round_label!r}")
