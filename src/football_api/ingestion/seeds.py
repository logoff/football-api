"""Typed loaders for the hand-curated seed files under `seeds/`."""

import re
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from football_api.domain.enums import CompetitionFormat, CompetitionScope, TeamKind
from football_api.infra.settings import get_settings


class _Seed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


Criterion = Literal[
    "goal_difference",
    "goals_for",
    "goal_ratio",
    "wins",
    "away_wins",
    "away_goals_for",
    "h2h_points",
    "h2h_goal_difference",
    "h2h_goals_for",
    "h2h_away_goals_for",
    "h2h_reapply",
    "opponents_points",
    "opponents_goal_difference",
    "opponents_goals_for",
]


class Points(_Seed):
    win: int
    draw: int
    loss: int = 0


class StandingsEra(_Seed):
    """Ranking rules from a season on: points per result and tie-breakers (standings design D4)."""

    start: int = Field(alias="from", description="First season's start year this era applies to")
    points: Points
    tiebreakers: list[Criterion]


class SquadSource(_Seed):
    style: Literal["more", "per-team"]
    files: list[str]


class SeasonSource(_Seed):
    label: str
    start_year: int
    file: str
    tz: str = Field(description="IANA zone of the file's kickoff times, or `inline`")
    json_file: str | None = Field(default=None, alias="json")
    events: str | None = Field(
        default=None, description="openfootball `-full` text file with the season's lineups, substitutions and cards"
    )
    squads: SquadSource | None = None
    wikipedia: str | None = Field(
        default=None, description="English Wikipedia article whose results grid verifies this season"
    )
    ranking: Literal["points", "points_per_game"] = "points"


class CompetitionSeed(_Seed):
    name: str
    country: str | None = None
    team_kind: TeamKind
    scope: CompetitionScope
    format: CompetitionFormat
    wikidata: str = Field(description="Wikidata QID; the competition's identity across syncs")
    seasons: list[SeasonSource] = Field(min_length=1)
    standings: list[StandingsEra] = Field(default_factory=list[StandingsEra])

    @model_validator(mode="after")
    def _unique_labels(self) -> "CompetitionSeed":
        labels = [s.label for s in self.seasons]
        if len(labels) != len(set(labels)):
            raise ValueError(f"{self.name}: duplicate season label")
        starts = [e.start for e in self.standings]
        if starts != sorted(set(starts)):
            raise ValueError(f"{self.name}: standings eras must have increasing `from` years")
        return self

    def era(self, season: SeasonSource) -> StandingsEra | None:
        """The ranking rules `season` uses: the last era starting at or before it."""
        eras = [e for e in self.standings if e.start <= season.start_year]
        return eras[-1] if eras else None


class ScopedSpelling(_Seed):
    """An openfootball spelling that names this team only in seasons starting in [from, until]:
    `Yugoslavia` is the 1920–1992 team until 1992 and FR Yugoslavia from 1993."""

    name: str
    start: int | None = Field(default=None, alias="from")
    until: int | None = None

    @property
    def key(self) -> str:
        """The spelling's external reference: `Yugoslavia @1993-`, `Yugoslavia @-1992`."""
        return f"{self.name} @{self.start or ''}-{self.until or ''}"

    def covers(self, year: int) -> bool:
        return (self.start is None or year >= self.start) and (self.until is None or year <= self.until)


def parse_scoped_key(key: str) -> tuple[str, int | None, int | None] | None:
    """`Yugoslavia @1993-` → ("Yugoslavia", 1993, None); None for a plain spelling."""
    m = re.fullmatch(r"(.+) @(\d*)-(\d*)", key)
    return (m[1], int(m[2]) if m[2] else None, int(m[3]) if m[3] else None) if m else None


class TeamSeed(_Seed):
    name: str
    kind: TeamKind
    country: str | None
    wikidata: str | None = None
    openfootball: list[str | ScopedSpelling] = Field(min_length=1)
    reference_wikidata: list[str] = Field(
        default_factory=list[str],
        description="Other Wikidata items that verification references use for this same side "
        "(the Dutch East Indies of 1938 as Indonesia); never used for identity",
    )

    @property
    def spelling_keys(self) -> list[str]:
        """The external-reference key of each spelling: the name itself, or a scoped key."""
        return [s if isinstance(s, str) else s.key for s in self.openfootball]


class PointsAdjustment(_Seed):
    """Points added to (or, negative, taken from) a team's table total, with why and where from."""

    competition: str = Field(description="Competition's Wikidata QID")
    season: str = Field(description="Season label")
    team: str = Field(description="Team's Wikidata QID, as in teams.yaml")
    points: int
    reason: str
    source: str
    effective: date | None = Field(default=None, description="Applies to tables as of this date on; whole season if absent")


class TieOrder(_Seed):
    """The final order of teams that results leave level (a play-off, lots, fair play)."""

    competition: str
    season: str
    order: list[str] = Field(min_length=2, description="Team QIDs, best first")
    reason: str
    source: str


class AwardedWinner(_Seed):
    """An awarded match the source records with a level score (no goals awarded) that still has a
    winner: the win and the loss count, the goals stay as recorded."""

    competition: str
    season: str
    home: str = Field(description="Home team's QID")
    away: str = Field(description="Away team's QID")
    winner: Literal["home", "away"]
    reason: str
    source: str


class StandingsSeeds(_Seed):
    adjustments: list[PointsAdjustment] = Field(default_factory=list[PointsAdjustment])
    orders: list[TieOrder] = Field(default_factory=list[TieOrder])
    awards: list[AwardedWinner] = Field(default_factory=list[AwardedWinner])

    def check(self, competitions: list[CompetitionSeed], teams: list[TeamSeed]) -> "StandingsSeeds":
        """Every entry must name a seeded competition, season and team (standings design D5)."""
        seasons = {(c.wikidata, s.label) for c in competitions for s in c.seasons}
        qids = {t.wikidata for t in teams if t.wikidata}
        entries: list[tuple[str, str, list[str]]] = [(a.competition, a.season, [a.team]) for a in self.adjustments]
        entries += [(o.competition, o.season, o.order) for o in self.orders]
        entries += [(w.competition, w.season, [w.home, w.away]) for w in self.awards]
        for competition, season, team_qids in entries:
            if (competition, season) not in seasons:
                raise ValueError(f"standings.yaml: no season {season!r} of competition {competition}")
            for qid in team_qids:
                if qid not in qids:
                    raise ValueError(f"standings.yaml: team {qid} is not in teams.yaml")
        return self


def _load(path: Path) -> object:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_competitions(path: Path | None = None) -> list[CompetitionSeed]:
    data = _load(path or get_settings().seeds_dir / "competitions.yaml")
    competitions = TypeAdapter(list[CompetitionSeed]).validate_python(data)
    qids = [c.wikidata for c in competitions]
    if len(qids) != len(set(qids)):
        raise ValueError("duplicate Wikidata QID in competitions.yaml")
    return competitions


def load_teams(path: Path | None = None) -> list[TeamSeed]:
    data = _load(path or get_settings().seeds_dir / "teams.yaml")
    teams = TypeAdapter(list[TeamSeed]).validate_python(data)
    seen_qids: dict[str, str] = {}
    seen_aliases: dict[str, str] = {}
    for team in teams:
        if team.wikidata:
            if team.wikidata in seen_qids:
                raise ValueError(f"Wikidata {team.wikidata} listed under both {seen_qids[team.wikidata]} and {team.name}")
            seen_qids[team.wikidata] = team.name
        for alias in team.spelling_keys:
            if alias in seen_aliases:
                raise ValueError(f"openfootball alias {alias!r} listed under both {seen_aliases[alias]} and {team.name}")
            seen_aliases[alias] = team.name
    scoped: dict[str, list[tuple[ScopedSpelling, str]]] = {}
    for team in teams:
        for spelling in team.openfootball:
            if isinstance(spelling, ScopedSpelling):
                scoped.setdefault(spelling.name, []).append((spelling, team.name))
    for name, ranges in scoped.items():
        if name in seen_aliases:
            raise ValueError(f"openfootball alias {name!r} is both plain ({seen_aliases[name]}) and year-scoped")
        for i, (a, team_a) in enumerate(ranges):
            for b, team_b in ranges[i + 1 :]:
                if (a.until is None or b.start is None or a.until >= b.start) and (b.until is None or a.start is None or b.until >= a.start):
                    raise ValueError(f"openfootball alias {name!r}: years overlap for {team_a} and {team_b}")
    for team in teams:
        for qid in team.reference_wikidata:
            if qid in seen_qids:
                raise ValueError(f"{team.name}: reference Wikidata {qid} is {seen_qids[qid]}'s own item")
    return teams


def load_standings(
    path: Path | None = None, competitions: list[CompetitionSeed] | None = None, teams: list[TeamSeed] | None = None
) -> StandingsSeeds:
    """`seeds/standings.yaml`, checked against the competition and team seeds."""
    seeds_dir = get_settings().seeds_dir
    path = path or seeds_dir / "standings.yaml"
    data: object = _load(path) if path.exists() else None
    seeds = StandingsSeeds.model_validate(data or {})
    return seeds.check(
        competitions if competitions is not None else load_competitions(),
        teams if teams is not None else load_teams(),
    )
