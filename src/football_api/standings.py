"""League and group tables from results (standings spec).

Pure functions over plain values: the API gathers a season's matches, rules and adjustments, and
these turn them into ordered rows. Nothing here touches the database.
"""

import re
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

from football_api.domain.enums import Stage
from football_api.ingestion.seeds import Criterion, StandingsEra

TeamId = uuid.UUID

# `Group A`, `Gruppe 3`, `First stage / Group B`, `Second Round / Group C`; not `Group, Matchday 1`
# nor `Group Stage / …` (the word after `Group` must be a lone letter or number).
_GROUP_NAME = re.compile(r"\b(?:Group|Gruppe)\s+([A-Z]|\d+)\b")


@dataclass(frozen=True)
class TableMatch:
    """A match of a table's stage; scores are None until played."""

    home: TeamId
    away: TeamId
    home_score: int | None
    away_score: int | None
    kickoff_utc: datetime
    stage: Stage
    round_label: str | None

    @property
    def played(self) -> bool:
        return self.home_score is not None and self.away_score is not None


@dataclass(frozen=True)
class TableKey:
    stage: Stage
    phase: int
    group: str | None


@dataclass
class Table:
    key: TableKey
    matches: list[TableMatch]

    @property
    def teams(self) -> set[TeamId]:
        return {t for m in self.matches for t in (m.home, m.away)}


def phase_of(round_label: str | None) -> int:
    return 2 if (round_label or "").startswith("Second Round") else 1


def group_of(round_label: str | None) -> str | None:
    names = _GROUP_NAME.findall(round_label or "")
    return names[-1] if names else None


def split_tables(matches: Iterable[TableMatch]) -> list[Table]:
    """One table per league stage, and one per (phase, group) of a group stage (design D3).

    Group matches whose label names no group join the named group both teams belong to, or else
    form groups of their own: the teams connected by the matches they played.
    """
    league: list[TableMatch] = []
    by_phase: dict[int, list[TableMatch]] = defaultdict(list)
    for m in matches:
        if m.stage is Stage.LEAGUE:
            league.append(m)
        elif m.stage is Stage.GROUP:
            by_phase[phase_of(m.round_label)].append(m)
    tables: list[Table] = []
    if league:
        tables.append(Table(TableKey(Stage.LEAGUE, 1, None), league))
    for phase in sorted(by_phase):
        named: dict[str, list[TableMatch]] = defaultdict(list)
        unnamed: list[TableMatch] = []
        for m in by_phase[phase]:
            name = group_of(m.round_label)
            (named[name] if name else unnamed).append(m)
        team_group = {t: name for name, ms in named.items() for m in ms for t in (m.home, m.away)}
        loose: list[TableMatch] = []
        for m in unnamed:
            g = team_group.get(m.home)
            if g is not None and team_group.get(m.away) == g:
                named[g].append(m)
            else:
                loose.append(m)
        for name in sorted(named, key=lambda n: (len(n), n)):  # A…L, then 1, 2, … 10
            tables.append(Table(TableKey(Stage.GROUP, phase, name), named[name]))
        for component in _components(loose):
            tables.append(Table(TableKey(Stage.GROUP, phase, None), component))
    return tables


def _components(matches: list[TableMatch]) -> list[list[TableMatch]]:
    """Matches split by the sets of teams they connect, ordered by each set's earliest kickoff."""
    parent: dict[TeamId, TeamId] = {}

    def find(t: TeamId) -> TeamId:
        parent.setdefault(t, t)
        while parent[t] != t:
            parent[t] = parent[parent[t]]
            t = parent[t]
        return t

    for m in matches:
        parent[find(m.home)] = find(m.away)
    groups: dict[TeamId, list[TableMatch]] = defaultdict(list)
    for m in matches:
        groups[find(m.home)].append(m)
    return sorted(groups.values(), key=lambda ms: (min(m.kickoff_utc for m in ms), sorted(str(t) for m in ms for t in (m.home, m.away))))


@dataclass
class Row:
    team: TeamId
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    adjustment: int = 0
    points: int = 0
    tied: bool = False
    position: int = 0

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


@dataclass(frozen=True)
class Rules:
    """The ranking rules a season uses (design D4)."""

    era: StandingsEra
    points_per_game: bool = False


@dataclass(frozen=True)
class Settled:
    """A curated order for teams that results can't separate (design D5)."""

    teams: tuple[TeamId, ...]


@dataclass
class _Context:
    rules: Rules
    results: list[TableMatch]
    rows: dict[TeamId, Row]
    name: Callable[[TeamId], str]


def rank(
    teams: Iterable[TeamId],
    results: Sequence[TableMatch],
    rules: Rules,
    *,
    adjustments: dict[TeamId, int] | None = None,
    settled: Sequence[Settled] = (),
    name: Callable[[TeamId], str] = str,
) -> list[Row]:
    """Rows of a table, ordered by points (or points per game) and then the era's tie-breakers.

    Teams still level after the last tie-breaker are `tied`; a `Settled` order naming exactly
    those teams decides their order, otherwise they are listed by name. A `Settled` order naming
    exactly a set of teams level on points (a title or relegation play-off) applies before any
    tie-breaker, and those teams are `tied` too.
    """
    played = [m for m in results if m.played]
    rows = {t: Row(t) for t in teams}
    points = rules.era.points
    for m in played:
        assert m.home_score is not None and m.away_score is not None
        for team, gf, ga in ((m.home, m.home_score, m.away_score), (m.away, m.away_score, m.home_score)):
            row = rows.setdefault(team, Row(team))
            row.played += 1
            row.goals_for += gf
            row.goals_against += ga
            if gf > ga:
                row.won += 1
                row.points += points.win
            elif gf == ga:
                row.drawn += 1
                row.points += points.draw
            else:
                row.lost += 1
                row.points += points.loss
    for team, delta in (adjustments or {}).items():
        if team in rows:
            rows[team].adjustment += delta
            rows[team].points += delta
    ctx = _Context(rules, played, rows, name)

    def primary(t: TeamId) -> Fraction:
        r = rows[t]
        if rules.points_per_game:
            return Fraction(r.points, r.played) if r.played else Fraction(0)
        return Fraction(r.points)

    ordered: list[list[TeamId]] = []
    for level in _buckets(list(rows), primary):
        decided = next((s.teams for s in settled if set(s.teams) == set(level)), None)
        if decided and len(level) > 1:
            ordered.append(list(decided))  # a play-off between teams level on points beats the tie-breakers
            continue
        ordered += _break(ctx, level, 0, None)
    out: list[Row] = []
    for chunk in ordered:
        if len(chunk) > 1:
            match = next((s.teams for s in settled if set(s.teams) == set(chunk)), None)
            chunk = list(match) if match else sorted(chunk, key=name)
            for t in chunk:
                rows[t].tied = True
        out += [rows[t] for t in chunk]
    for i, row in enumerate(out, start=1):
        row.position = i
    return out


def _buckets(teams: list[TeamId], value: Callable[[TeamId], Fraction]) -> list[list[TeamId]]:
    """Teams grouped by equal value, best (highest) first."""
    by: dict[Fraction, list[TeamId]] = defaultdict(list)
    for t in teams:
        by[value(t)].append(t)
    return [by[v] for v in sorted(by, reverse=True)]


def _block_start(criteria: Sequence[Criterion], i: int) -> int:
    """Index of the first head-to-head criterion of the block ending before `h2h_reapply` at i."""
    j = i
    while j > 0 and criteria[j - 1].startswith("h2h_") and criteria[j - 1] != "h2h_reapply":
        j -= 1
    return j


def _break(ctx: _Context, tied: list[TeamId], i: int, origin: frozenset[TeamId] | None) -> list[list[TeamId]]:
    """Order a set of teams level so far, from criterion i on; each inner list is still level.

    Head-to-head criteria are computed among `origin`, the teams level when the head-to-head
    block began; `h2h_reapply` restarts the block among a smaller subset still level (UEFA).
    """
    if len(tied) == 1:
        return [tied]
    criteria = ctx.rules.era.tiebreakers
    if i == len(criteria):
        return [tied]
    c = criteria[i]
    if c == "h2h_reapply":
        if origin is not None and len(tied) < len(origin):
            return _break(ctx, tied, _block_start(criteria, i), frozenset(tied))
        return _break(ctx, tied, i + 1, None)
    is_h2h = c.startswith("h2h_")
    if is_h2h and (origin is None or i == 0 or not criteria[i - 1].startswith("h2h_")):
        origin = frozenset(tied)
    among = origin if is_h2h and origin is not None else frozenset(tied)
    out: list[list[TeamId]] = []
    for level in _buckets(tied, lambda t: _metric(ctx, c, t, among)):
        out += _break(ctx, level, i + 1, origin if is_h2h else None)
    return out


def _metric(ctx: _Context, criterion: Criterion, team: TeamId, among: frozenset[TeamId]) -> Fraction:
    rows = ctx.rows
    if criterion == "goal_difference":
        return Fraction(rows[team].goal_difference)
    if criterion == "goals_for":
        return Fraction(rows[team].goals_for)
    if criterion == "goal_ratio":
        r = rows[team]
        return Fraction(r.goals_for, r.goals_against) if r.goals_against else Fraction(10**9 + r.goals_for)
    if criterion == "wins":
        return Fraction(rows[team].won)
    if criterion in ("away_wins", "away_goals_for"):
        away = [m for m in ctx.results if m.away == team]
        if criterion == "away_goals_for":
            return Fraction(sum(m.away_score or 0 for m in away))
        return Fraction(sum(1 for m in away if (m.away_score or 0) > (m.home_score or 0)))
    if criterion.startswith("h2h_"):
        mini = [m for m in ctx.results if m.home in among and m.away in among]
        return _mini_metric(ctx, criterion[4:], team, mini)
    if criterion.startswith("opponents_"):
        opponents = [m.away if m.home == team else m.home for m in ctx.results if team in (m.home, m.away)]
        what = criterion[len("opponents_") :]
        if what == "points":
            return Fraction(sum(rows[o].points - rows[o].adjustment for o in opponents))
        if what == "goal_difference":
            return Fraction(sum(rows[o].goal_difference for o in opponents))
        return Fraction(sum(rows[o].goals_for for o in opponents))
    raise ValueError(f"unknown tie-breaker {criterion!r}")


def _mini_metric(ctx: _Context, what: str, team: TeamId, mini: list[TableMatch]) -> Fraction:
    """Points, goal difference, goals or away goals of `team` in the matches among tied teams."""
    points = ctx.rules.era.points
    total = 0
    for m in mini:
        if team not in (m.home, m.away):
            continue
        assert m.home_score is not None and m.away_score is not None
        home = m.home == team
        gf, ga = (m.home_score, m.away_score) if home else (m.away_score, m.home_score)
        if what == "points":
            total += points.win if gf > ga else points.draw if gf == ga else points.loss
        elif what == "goal_difference":
            total += gf - ga
        elif what == "goals_for":
            total += gf
        elif what == "away_goals_for":
            total += 0 if home else gf
    return Fraction(total)
