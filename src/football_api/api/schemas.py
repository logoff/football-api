"""Response models. Timestamps serialise as ISO 8601 UTC with a `Z` suffix."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

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
    VerificationReference,
    VerificationStatus,
)

UtcDatetime = Annotated[
    datetime,
    PlainSerializer(lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ"), return_type=str, when_used="json"),
]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CompetitionOut(_Out):
    id: uuid.UUID
    name: str = Field(examples=["Premier League"])
    country: str | None = Field(description="ISO 3166-1 alpha-2, or a UK subdivision (GB-ENG); null for international", examples=["GB-ENG"])
    team_kind: TeamKind
    scope: CompetitionScope
    format: CompetitionFormat = Field(
        description="LEAGUE (round-robin), CUP (knockout open to the national pyramid), LEAGUE_CUP (knockout for league "
        "clubs only), SUPER_CUP (champions' play-off), TOURNAMENT (group or league phase, then knockouts)"
    )


_EVENTS_SOURCES = (
    "Sources with events: every FIFA World Cup (1930–2026) and FIFA Club World Cup (2000–2025), and the 2025-26 "
    "Premier League, La Liga, Bundesliga, Serie A and Ligue 1"
)


class SeasonCoverage(BaseModel):
    scorers: Coverage = Field(description="`full` when the source lists goal scorers for this season")
    players: Coverage = Field(description="`full` when the source publishes squad lists for this season")
    lineups: Coverage = Field(description=f"`full` when the source lists the line-ups of this season's matches. {_EVENTS_SOURCES}")
    substitutions: Coverage = Field(
        description="`full` when the source lists substitutions. `none` for Club World Cup 2018 and 2019, whose "
        "source lists starters only, and for World Cups before 1970, which allowed no substitutions"
    )
    cards: Coverage = Field(
        description="`full` when the source lists cards. A match without cards in a `full` season had none"
    )


class SeasonOut(_Out):
    id: uuid.UUID
    competition_id: uuid.UUID
    label: str = Field(examples=["2024-25"])
    starts_on: date | None
    ends_on: date | None
    status: SeasonStatus
    coverage: SeasonCoverage


class TeamSeasonOut(BaseModel):
    season_id: uuid.UUID
    competition_id: uuid.UUID
    label: str = Field(examples=["2024-25"])


class TeamOut(_Out):
    id: uuid.UUID
    name: str = Field(examples=["Manchester United"])
    country: str | None
    kind: TeamKind
    seasons: list[TeamSeasonOut] | None = Field(default=None, description="Present with `expand=seasons`")


class PlayerOut(_Out):
    id: uuid.UUID
    display_name: str = Field(examples=["Lionel Messi"])
    full_name: str | None
    given_name: str | None = Field(description="Only when the source marks the surname; never guessed")
    family_name: str | None
    birth_year: int | None
    dob: date | None
    nationality: str | None
    position: str | None = Field(examples=["FW"])


class VenueOut(_Out):
    id: uuid.UUID
    name: str = Field(examples=["Lusail Stadium"])
    city: str | None
    country: str | None


class PlayerRef(BaseModel):
    id: uuid.UUID
    display_name: str


class GoalOut(BaseModel):
    ordinal: int
    side: Side
    player: PlayerRef | None = Field(description="Resolved squad player; null when the source name is ambiguous")
    name: str = Field(description="Scorer name as shown (player's display name, or the source text)")
    minute: int | None
    added_minute: int | None = Field(description="Added time, e.g. 5 for `90+5'`")
    is_penalty: bool
    is_own_goal: bool


_EVENT_PLAYER = "Squad player the source name resolves to; null without squads or when the name is ambiguous"


class LineupEntryOut(BaseModel):
    player: PlayerRef | None = Field(description=_EVENT_PLAYER)
    name: str = Field(description="Player name as the source gives it", examples=["Reece James"])
    role: LineupRole = Field(description="`STARTER`, or `SUBSTITUTE` for a player who came on; unused substitutes aren't listed")
    line: int | None = Field(description="1-based line group the source lists a starter in (goalkeeper first); null for substitutes")
    is_captain: bool


class LineupOut(BaseModel):
    formation: str | None = Field(
        description="Starters per source line group after the goalkeeper, e.g. `4-3-3`. It reflects how the source "
        "groups the line-up, not a verified tactical shape; null when the source doesn't group it",
        examples=["4-3-3"],
    )
    entries: list[LineupEntryOut] = Field(description="Starters in source order, then the substitutes who came on")


class LineupsOut(BaseModel):
    home: LineupOut
    away: LineupOut


class SubstitutionOut(BaseModel):
    side: Side
    minute: int
    added_minute: int | None = Field(description="Added time, e.g. 5 for `90+5'`")
    player_off: PlayerRef | None = Field(description=_EVENT_PLAYER)
    player_off_name: str
    player_on: PlayerRef | None = Field(description=_EVENT_PLAYER)
    player_on_name: str


class CardOut(BaseModel):
    side: Side
    minute: int
    added_minute: int | None = Field(description="Added time, e.g. 2 for `90+2'`")
    kind: CardKind = Field(description="`SECOND_YELLOW` is the sending-off; the first yellow is its own `YELLOW` card")
    player: PlayerRef | None = Field(description=_EVENT_PLAYER)
    name: str


class MatchCoverage(BaseModel):
    scorers: Coverage
    lineups: Coverage = Field(description="The season's `lineups` coverage")
    substitutions: Coverage = Field(description="The season's `substitutions` coverage")
    cards: Coverage = Field(description="The season's `cards` coverage")


class MatchVerificationOut(BaseModel):
    status: VerificationStatus = Field(
        description="`VERIFIED` both sources agree; `MISMATCH` they differ; "
        "`UNCONFIRMED` the reference has no result yet; `SOURCE_BEHIND` only the reference has one"
    )
    reference: VerificationReference = Field(description="The independent source compared against")
    checked_at: UtcDatetime


class MatchOut(BaseModel):
    id: uuid.UUID
    competition_id: uuid.UUID
    season_id: uuid.UUID
    stage: Stage
    matchday: int | None = Field(description="Matchday, or the round's number when `stage` is ROUND")
    occurrence: int = Field(
        description="1, or 2+ for a pairing played again with the same home team in the same stage (a cup re-replay)",
        examples=[1],
    )
    round_label: str = Field(description="Round as written in the source", examples=["First stage / Group A"])
    kickoff_utc: UtcDatetime
    original_kickoff_utc: UtcDatetime | None = Field(description="Set when a later sync observed the kickoff move")
    status: MatchStatus
    home_team_id: uuid.UUID
    away_team_id: uuid.UUID
    venue_id: uuid.UUID | None
    home_score: int | None = Field(description="Score at end of play, including extra time")
    away_score: int | None
    decided_by: DecidedBy | None
    home_pens: int | None
    away_pens: int | None
    awarded: bool = Field(
        description="Decided off the pitch (forfeit or disciplinary decision), as the source marks it; the score is "
        "the one the source records, which can be the score when play stopped"
    )
    referee: str | None = Field(description="Referee's name, when the source gives it", examples=["Alireza Faghani"])
    attendance: int | None = Field(description="Spectators, when the source gives it", examples=[81118])
    coverage: MatchCoverage
    verification: MatchVerificationOut | None = Field(
        description="Score check against an independent open reference; null when the match isn't verified. "
        "Only the outcome is shown, never the reference's own values"
    )
    home_team: TeamOut | None = Field(default=None, description="Present with `expand=teams`")
    away_team: TeamOut | None = Field(default=None, description="Present with `expand=teams`")
    venue: VenueOut | None = Field(default=None, description="Present with `expand=venue`")
    scorers: list[GoalOut] | None = Field(default=None, description="Present with `expand=scorers`")
    lineups: LineupsOut | None = Field(default=None, description="Present with `expand=lineups`")
    substitutions: list[SubstitutionOut] | None = Field(
        default=None, description="Present with `expand=substitutions`; ordered by minute, then source order"
    )
    cards: list[CardOut] | None = Field(
        default=None, description="Present with `expand=cards`; ordered by minute, then source order"
    )


class Page[T](BaseModel):
    data: list[T]
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page; null on the last page")


class PlayerCoverage(BaseModel):
    players: Coverage


class PlayerPage(Page[PlayerOut]):
    coverage: PlayerCoverage | None = Field(
        default=None, description="Present when filtering by `team_id` and `season_id`"
    )


class StandingAdjustmentOut(BaseModel):
    points: int = Field(examples=[-8], description="Added to the team's total; negative for a deduction")
    reason: str
    source: str = Field(description="Where the adjustment is documented")


class StandingRowOut(BaseModel):
    position: int
    team_id: uuid.UUID
    team: TeamOut | None = Field(default=None, description="Present with `expand=teams`")
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int = Field(description="Including adjustments")
    adjustments: list[StandingAdjustmentOut]
    tied: bool = Field(
        description="Results alone don't separate this team from a neighbour: the order then comes from a "
        "curated decision (play-off, lots, fair play) or, failing one, team name"
    )
    verification: MatchVerificationOut | None = Field(
        default=None,
        description="This row against the reference's final table; null for provisional tables and with `as_of`",
    )


class StandingTableOut(BaseModel):
    stage: Stage = Field(description="`LEAGUE` for a league or league phase, `GROUP` for a group stage")
    phase: int = Field(description="1, or 2 for a second group round (World Cup 1974–1982)")
    group: str | None = Field(examples=["A"], description="Null for a league, and for groups the source doesn't name")
    status: Literal["final", "provisional"]
    rows: list[StandingRowOut]


class StandingsOut(BaseModel):
    season_id: uuid.UUID
    as_of: date | None = Field(description="The date the tables were computed for; null for the latest results")
    tables: list[StandingTableOut]
