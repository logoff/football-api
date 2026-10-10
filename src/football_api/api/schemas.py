"""Response models. Timestamps serialise as ISO 8601 UTC with a `Z` suffix."""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from football_api.domain.enums import (
    CompetitionScope,
    Coverage,
    DecidedBy,
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


class SeasonCoverage(BaseModel):
    scorers: Coverage = Field(description="`full` when the source lists goal scorers for this season")
    players: Coverage = Field(description="`full` when the source publishes squad lists for this season")


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


class GoalPlayerRef(BaseModel):
    id: uuid.UUID
    display_name: str


class GoalOut(BaseModel):
    ordinal: int
    side: Side
    player: GoalPlayerRef | None = Field(description="Resolved squad player; null when the source name is ambiguous")
    name: str = Field(description="Scorer name as shown (player's display name, or the source text)")
    minute: int | None
    added_minute: int | None = Field(description="Added time, e.g. 5 for `90+5'`")
    is_penalty: bool
    is_own_goal: bool


class MatchCoverage(BaseModel):
    scorers: Coverage


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
    matchday: int | None
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
    coverage: MatchCoverage
    verification: MatchVerificationOut | None = Field(
        description="Score check against an independent open reference; null when the match isn't verified. "
        "Only the outcome is shown, never the reference's own values"
    )
    home_team: TeamOut | None = Field(default=None, description="Present with `expand=teams`")
    away_team: TeamOut | None = Field(default=None, description="Present with `expand=teams`")
    venue: VenueOut | None = Field(default=None, description="Present with `expand=venue`")
    scorers: list[GoalOut] | None = Field(default=None, description="Present with `expand=scorers`")


class Page[T](BaseModel):
    data: list[T]
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page; null on the last page")


class PlayerCoverage(BaseModel):
    players: Coverage


class PlayerPage(Page[PlayerOut]):
    coverage: PlayerCoverage | None = Field(
        default=None, description="Present when filtering by `team_id` and `season_id`"
    )
