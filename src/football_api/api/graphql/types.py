"""Schema types, built from ORM rows (design D3). Field meanings follow the REST models in `api/schemas.py`."""

import enum
import uuid
from datetime import date, datetime
from typing import Annotated, Self

import strawberry
from strawberry import Info

from football_api.api import queries
from football_api.api.graphql.connection import Connection, PageInfo, connection, edges_of, page_size
from football_api.api.graphql.context import Context
from football_api.domain.enums import (
    CardKind,
    CompetitionFormat,
    CompetitionScope,
    Coverage,
    DecidedBy,
    LineupRole,
    MatchStatus,
    SeasonStatus,
    Side,
    Stage,
    TeamKind,
    VerificationAspect,
    VerificationReference,
    VerificationStatus,
)
from football_api.infra import models as m
from football_api.season_tables import season_tables

for _enum in (CardKind, CompetitionFormat, CompetitionScope, DecidedBy, LineupRole, MatchStatus, SeasonStatus, Side, Stage, TeamKind, VerificationStatus):
    strawberry.enum(_enum)

# Maps `datetime` in the schema (`StrawberryConfig.scalar_map`): REST's `Z` format.
UTC_DATETIME = strawberry.scalar(
    name="DateTime",
    description="UTC timestamp, ISO 8601 with a `Z` suffix",
    serialize=lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ"),
    parse_value=lambda v: datetime.fromisoformat(v),
)


# REST writes these two in lower case; GraphQL enum values follow REST (graphql-api spec, Parity with REST).
@strawberry.enum(name="Coverage")
class CoverageValue(enum.Enum):
    FULL = strawberry.enum_value(Coverage.FULL.value, name="full")
    NONE = strawberry.enum_value(Coverage.NONE.value, name="none")


@strawberry.enum(name="VerificationReference")
class ReferenceValue(enum.Enum):
    WIKIPEDIA = strawberry.enum_value(VerificationReference.WIKIPEDIA.value, name="wikipedia")


def _coverage(value: Coverage) -> CoverageValue:
    return CoverageValue(value.value)


type GInfo = Info[Context, None]


# --- catalog -----------------------------------------------------------------------


@strawberry.type
class Competition:
    id: uuid.UUID
    name: str
    country: str | None
    team_kind: TeamKind
    scope: CompetitionScope
    format: CompetitionFormat

    @classmethod
    def of(cls, c: m.Competition) -> Self:
        return cls(id=c.id, name=c.name, country=c.country, team_kind=c.team_kind, scope=c.scope, format=c.format)

    @strawberry.field
    async def seasons(self, info: GInfo, first: int | None = None, after: str | None = None) -> Connection["Season"] | None:
        async with info.context.db() as s:
            listing = await queries.seasons(s, competition_id=self.id, limit=page_size(first), cursor=after)
        return connection(listing, Season.of)


@strawberry.type
class SeasonCoverage:
    scorers: CoverageValue
    players: CoverageValue
    lineups: CoverageValue
    substitutions: CoverageValue
    cards: CoverageValue


@strawberry.type
class Season:
    id: uuid.UUID
    competition_id: uuid.UUID
    label: str
    starts_on: date | None
    ends_on: date | None
    status: SeasonStatus
    coverage: SeasonCoverage
    row: strawberry.Private[m.Season]

    @classmethod
    def of(cls, s: m.Season) -> Self:
        return cls(
            id=s.id,
            competition_id=s.competition_id,
            label=s.label,
            starts_on=s.starts_on,
            ends_on=s.ends_on,
            status=s.status,
            coverage=SeasonCoverage(
                scorers=_coverage(s.scorers_coverage),
                players=_coverage(s.players_coverage),
                lineups=_coverage(s.lineups_coverage),
                substitutions=_coverage(s.substitutions_coverage),
                cards=_coverage(s.cards_coverage),
            ),
            row=s,
        )

    @strawberry.field
    async def competition(self, info: GInfo) -> Competition | None:
        c = await info.context.loaders.competition.load(self.competition_id)
        return Competition.of(c) if c else None

    @strawberry.field
    async def teams(
        self, info: GInfo, kind: TeamKind | None = None, first: int | None = None, after: str | None = None
    ) -> Connection["Team"] | None:
        async with info.context.db() as s:
            listing = await queries.teams(
                s, competition_id=None, season_id=self.id, kind=kind, limit=page_size(first), cursor=after
            )
        return connection(listing, Team.of)

    @strawberry.field
    async def matches(
        self,
        info: GInfo,
        team_id: uuid.UUID | None = None,
        stage: Stage | None = None,
        from_: Annotated[date | None, strawberry.argument(name="from")] = None,
        to: date | None = None,
        verification: VerificationStatus | None = None,
        events_verification: VerificationStatus | None = None,
        first: int | None = None,
        after: str | None = None,
    ) -> Connection["Match"] | None:
        async with info.context.db() as s:
            listing = await queries.matches(
                s,
                season_id=self.id,
                team_id=team_id,
                stage=stage,
                from_=from_,
                to=to,
                verification=verification,
                events_verification=events_verification,
                limit=page_size(first),
                cursor=after,
            )
        return connection(listing, Match.of)

    @strawberry.field(description="Tables computed from the season's results; `asOf` in the season's time zone")
    async def standings(self, info: GInfo, as_of: date | None = None) -> "Standings":
        async with info.context.db() as s:
            tables = await season_tables(s, self.row, as_of)
            checks = {} if as_of is not None else await queries.standing_checks(s, self.id)
        return Standings(
            season_id=self.id,
            as_of=as_of,
            tables=[
                StandingTable(
                    stage=t.key.stage,
                    phase=t.key.phase,
                    group=t.key.group,
                    status=t.status,
                    rows=[
                        StandingRow(
                            position=r.position,
                            team_id=r.team,
                            played=r.played,
                            won=r.won,
                            drawn=r.drawn,
                            lost=r.lost,
                            goals_for=r.goals_for,
                            goals_against=r.goals_against,
                            goal_difference=r.goal_difference,
                            points=r.points,
                            adjustments=[
                                StandingAdjustment(points=a.points, reason=a.reason, source=a.source)
                                for a in t.adjustments.get(r.team, [])
                            ],
                            tied=r.tied,
                            verification=Verification.of(checks.get((r.team, t.key.stage, t.key.phase, t.key.group or "")))
                            if t.status == "final"
                            else None,
                        )
                        for r in t.rows
                    ],
                )
                for t in tables
            ],
        )


@strawberry.type
class Team:
    id: uuid.UUID
    name: str
    country: str | None
    kind: TeamKind

    @classmethod
    def of(cls, t: m.Team) -> Self:
        return cls(id=t.id, name=t.name, country=t.country, kind=t.kind)

    @strawberry.field(description="The seasons the team took part in")
    async def seasons(self, info: GInfo) -> list[Season]:
        return [Season.of(s) for s in await info.context.loaders.team_seasons.load(self.id)]

    @strawberry.field(description="Squad players; with `seasonId`, that season's squad and its coverage")
    async def players(
        self, info: GInfo, season_id: uuid.UUID | None = None, first: int | None = None, after: str | None = None
    ) -> "PlayerConnection | None":
        return await _players(info, team_id=self.id, season_id=season_id, competition_id=None, first=first, after=after)


@strawberry.type
class Player:
    id: uuid.UUID
    display_name: str
    full_name: str | None
    given_name: str | None
    family_name: str | None
    birth_year: int | None
    dob: date | None
    nationality: str | None
    position: str | None

    @classmethod
    def of(cls, p: m.Player) -> Self:
        return cls(
            id=p.id,
            display_name=p.display_name,
            full_name=p.full_name,
            given_name=p.given_name,
            family_name=p.family_name,
            birth_year=p.birth_year,
            dob=p.dob,
            nationality=p.nationality,
            position=p.position,
        )


@strawberry.type
class PlayerCoverage:
    players: CoverageValue


@strawberry.type
class PlayerConnection:
    edges: list["PlayerEdge"]
    page_info: PageInfo
    coverage: PlayerCoverage | None = strawberry.field(description="Present when filtering by team and season")


@strawberry.type
class PlayerEdge:
    cursor: str
    node: Player


async def _players(
    info: GInfo,
    *,
    team_id: uuid.UUID | None,
    season_id: uuid.UUID | None,
    competition_id: uuid.UUID | None,
    first: int | None,
    after: str | None,
) -> PlayerConnection:
    async with info.context.db() as s:
        listing = await queries.players(
            s, team_id=team_id, season_id=season_id, competition_id=competition_id, limit=page_size(first), cursor=after
        )
        coverage = (
            PlayerCoverage(players=_coverage(await queries.squad_coverage(s, season_id))) if team_id and season_id else None
        )
    edges, info_ = edges_of(listing, Player.of)
    return PlayerConnection(
        edges=[PlayerEdge(cursor=e.cursor, node=e.node) for e in edges], page_info=info_, coverage=coverage
    )


@strawberry.type
class Venue:
    id: uuid.UUID
    name: str
    city: str | None
    country: str | None

    @classmethod
    def of(cls, v: m.Venue) -> Self:
        return cls(id=v.id, name=v.name, city=v.city, country=v.country)


# --- matches -----------------------------------------------------------------------


@strawberry.type
class Verification:
    status: VerificationStatus
    reference: ReferenceValue
    checked_at: datetime

    @classmethod
    def of(cls, v: m.MatchVerification | m.StandingVerification | None) -> Self | None:
        return cls(status=v.status, reference=ReferenceValue(v.reference.value), checked_at=v.checked_at) if v else None


async def _player(info: GInfo, player_id: uuid.UUID | None) -> Player | None:
    p = await info.context.loaders.player.load(player_id) if player_id else None
    return Player.of(p) if p else None


@strawberry.type
class Goal:
    ordinal: int
    side: Side
    name: str = strawberry.field(description="Scorer name as shown (player's display name, or the source text)")
    minute: int | None
    added_minute: int | None
    is_penalty: bool
    is_own_goal: bool
    player_id: strawberry.Private[uuid.UUID | None]

    @strawberry.field(description="Resolved squad player; null when the source name is ambiguous")
    async def player(self, info: GInfo) -> Player | None:
        return await _player(info, self.player_id)


@strawberry.type
class LineupEntry:
    name: str
    role: LineupRole
    line: int | None
    is_captain: bool
    player_id: strawberry.Private[uuid.UUID | None]

    @strawberry.field
    async def player(self, info: GInfo) -> Player | None:
        return await _player(info, self.player_id)


@strawberry.type
class Lineup:
    formation: str | None
    entries: list[LineupEntry]

    @classmethod
    def of(cls, rows: list[m.LineupEntry]) -> Self:
        return cls(
            formation=queries.formation(rows),
            entries=[
                LineupEntry(name=e.player_name, role=e.role, line=e.line_index, is_captain=e.is_captain, player_id=e.player_id)
                for e in rows
            ],
        )


@strawberry.type
class Lineups:
    home: Lineup
    away: Lineup


@strawberry.type
class Substitution:
    side: Side
    minute: int
    added_minute: int | None
    player_off_name: str
    player_on_name: str
    player_off_id: strawberry.Private[uuid.UUID | None]
    player_on_id: strawberry.Private[uuid.UUID | None]

    @strawberry.field
    async def player_off(self, info: GInfo) -> Player | None:
        return await _player(info, self.player_off_id)

    @strawberry.field
    async def player_on(self, info: GInfo) -> Player | None:
        return await _player(info, self.player_on_id)


@strawberry.type
class Card:
    side: Side
    minute: int
    added_minute: int | None
    kind: CardKind
    name: str
    player_id: strawberry.Private[uuid.UUID | None]

    @strawberry.field
    async def player(self, info: GInfo) -> Player | None:
        return await _player(info, self.player_id)


@strawberry.type
class MatchCoverage:
    scorers: CoverageValue
    lineups: CoverageValue
    substitutions: CoverageValue
    cards: CoverageValue


@strawberry.type
class Match:
    id: uuid.UUID
    competition_id: uuid.UUID
    season_id: uuid.UUID
    stage: Stage
    matchday: int | None
    occurrence: int
    round_label: str
    kickoff_utc: datetime
    original_kickoff_utc: datetime | None
    status: MatchStatus
    home_team_id: uuid.UUID
    away_team_id: uuid.UUID
    venue_id: uuid.UUID | None
    home_score: int | None
    away_score: int | None
    decided_by: DecidedBy | None
    home_pens: int | None
    away_pens: int | None
    awarded: bool
    referee: str | None
    attendance: int | None
    coverage: MatchCoverage
    season_row: strawberry.Private[m.Season]

    @classmethod
    def of(cls, row: queries.MatchRow) -> Self:
        x, season = row
        return cls(
            id=x.id,
            competition_id=season.competition_id,
            season_id=x.season_id,
            stage=x.stage,
            matchday=x.matchday,
            occurrence=x.occurrence,
            round_label=x.round_label,
            kickoff_utc=x.kickoff_utc,
            original_kickoff_utc=x.original_kickoff_utc,
            status=x.status,
            home_team_id=x.home_team_id,
            away_team_id=x.away_team_id,
            venue_id=x.venue_id,
            home_score=x.home_score,
            away_score=x.away_score,
            decided_by=x.decided_by,
            home_pens=x.home_pens,
            away_pens=x.away_pens,
            awarded=x.awarded,
            referee=x.referee_name,
            attendance=x.attendance,
            coverage=MatchCoverage(
                scorers=_coverage(season.scorers_coverage),
                lineups=_coverage(season.lineups_coverage),
                substitutions=_coverage(season.substitutions_coverage),
                cards=_coverage(season.cards_coverage),
            ),
            season_row=season,
        )

    @strawberry.field
    def season(self) -> Season:
        return Season.of(self.season_row)

    @strawberry.field
    async def competition(self, info: GInfo) -> Competition | None:
        c = await info.context.loaders.competition.load(self.competition_id)
        return Competition.of(c) if c else None

    @strawberry.field
    async def home_team(self, info: GInfo) -> Team | None:
        t = await info.context.loaders.team.load(self.home_team_id)
        return Team.of(t) if t else None

    @strawberry.field
    async def away_team(self, info: GInfo) -> Team | None:
        t = await info.context.loaders.team.load(self.away_team_id)
        return Team.of(t) if t else None

    @strawberry.field
    async def venue(self, info: GInfo) -> Venue | None:
        v = await info.context.loaders.venue.load(self.venue_id) if self.venue_id else None
        return Venue.of(v) if v else None

    @strawberry.field(description="Score check against an independent open reference; null when not verified")
    async def verification(self, info: GInfo) -> Verification | None:
        return Verification.of((await info.context.loaders.verifications.load(self.id)).get(VerificationAspect.RESULT))

    @strawberry.field(description="Line-ups, substitutions and cards checked against the reference's line-up table")
    async def events_verification(self, info: GInfo) -> Verification | None:
        return Verification.of((await info.context.loaders.verifications.load(self.id)).get(VerificationAspect.EVENTS))

    @strawberry.field
    async def scorers(self, info: GInfo) -> list[Goal]:
        return [
            Goal(
                ordinal=g.ordinal,
                side=g.side,
                name=name or g.scorer_name or "",
                minute=g.minute,
                added_minute=g.added_minute,
                is_penalty=g.is_penalty,
                is_own_goal=g.is_own_goal,
                player_id=g.scorer_player_id if name else None,
            )
            for g, name in await info.context.loaders.goals.load(self.id)
        ]

    @strawberry.field
    async def lineups(self, info: GInfo) -> Lineups:
        sides = await info.context.loaders.lineups.load(self.id)
        return Lineups(home=Lineup.of(sides.get(Side.HOME, [])), away=Lineup.of(sides.get(Side.AWAY, [])))

    @strawberry.field(description="Ordered by minute, then source order")
    async def substitutions(self, info: GInfo) -> list[Substitution]:
        return [
            Substitution(
                side=s.side,
                minute=s.minute,
                added_minute=s.added_minute,
                player_off_name=s.player_off_name,
                player_on_name=s.player_on_name,
                player_off_id=s.player_off_id,
                player_on_id=s.player_on_id,
            )
            for s in await info.context.loaders.substitutions.load(self.id)
        ]

    @strawberry.field(description="Ordered by minute, then source order")
    async def cards(self, info: GInfo) -> list[Card]:
        return [
            Card(side=c.side, minute=c.minute, added_minute=c.added_minute, kind=c.kind, name=c.player_name, player_id=c.player_id)
            for c in await info.context.loaders.cards.load(self.id)
        ]


# --- standings ---------------------------------------------------------------------


@strawberry.type
class StandingAdjustment:
    points: int
    reason: str
    source: str


@strawberry.type
class StandingRow:
    position: int
    team_id: uuid.UUID
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    adjustments: list[StandingAdjustment]
    tied: bool
    verification: Verification | None

    @strawberry.field
    async def team(self, info: GInfo) -> Team | None:
        t = await info.context.loaders.team.load(self.team_id)
        return Team.of(t) if t else None


@strawberry.type
class StandingTable:
    stage: Stage
    phase: int
    group: str | None
    status: str = strawberry.field(description="`final` or `provisional`")
    rows: list[StandingRow]


@strawberry.type
class Standings:
    season_id: uuid.UUID
    as_of: date | None
    tables: list[StandingTable]
