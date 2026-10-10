"""SQLAlchemy models. See design.md, "Domain model" and "ID principles".

Every entity has a server-generated uuidv7 primary key (PostgreSQL 18). External
identifiers never live on entity tables; they go in ``external_ref``. No row carries
created/updated timestamps, so an unchanged re-sync leaves rows byte-for-byte equal.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    MetaData,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from football_api.domain.enums import (
    CompetitionScope,
    Coverage,
    DecidedBy,
    EntityType,
    MatchStatus,
    SeasonStatus,
    Side,
    Stage,
    TeamKind,
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _enum[E: StrEnum](enum_cls: type[E], name: str) -> SAEnum:
    def values(members: type[E]) -> list[str]:
        return [m.value for m in members]

    return SAEnum(enum_cls, name=name, values_callable=values)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, server_default=text("uuidv7()"))


class Competition(Base):
    __tablename__ = "competition"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(128))
    country: Mapped[str | None] = mapped_column(String(6))
    team_kind: Mapped[TeamKind] = mapped_column(_enum(TeamKind, "team_kind"))
    scope: Mapped[CompetitionScope] = mapped_column(_enum(CompetitionScope, "competition_scope"))


class Season(Base):
    __tablename__ = "season"
    __table_args__ = (UniqueConstraint("competition_id", "label"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    competition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("competition.id"))
    label: Mapped[str] = mapped_column(String(16))
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[SeasonStatus] = mapped_column(_enum(SeasonStatus, "season_status"))
    scorers_coverage: Mapped[Coverage] = mapped_column(_enum(Coverage, "coverage"))
    players_coverage: Mapped[Coverage] = mapped_column(_enum(Coverage, "coverage"))


class Team(Base):
    __tablename__ = "team"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(128))
    country: Mapped[str | None] = mapped_column(String(6))
    kind: Mapped[TeamKind] = mapped_column(_enum(TeamKind, "team_kind"))


class TeamSeason(Base):
    __tablename__ = "team_season"

    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("team.id"), primary_key=True)
    season_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("season.id"), primary_key=True, index=True
    )


class Venue(Base):
    __tablename__ = "venue"
    __table_args__ = (UniqueConstraint("name", "city", postgresql_nulls_not_distinct=True),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(128))
    city: Mapped[str | None] = mapped_column(String(128))
    country: Mapped[str | None] = mapped_column(String(6))


class Player(Base):
    __tablename__ = "player"

    id: Mapped[uuid.UUID] = _uuid_pk()
    display_name: Mapped[str] = mapped_column(String(128))
    full_name: Mapped[str | None] = mapped_column(String(160))
    given_name: Mapped[str | None] = mapped_column(String(128))
    family_name: Mapped[str | None] = mapped_column(String(128))
    birth_year: Mapped[int | None] = mapped_column(SmallInteger)
    dob: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(6))
    position: Mapped[str | None] = mapped_column(String(8))


class PlayerTeamSeason(Base):
    """Squad membership. Natural key of a player is (team, season, display_name)."""

    __tablename__ = "player_team_season"
    __table_args__ = (UniqueConstraint("team_id", "season_id", "player_id"),)

    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("player.id"), primary_key=True)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("team.id"), primary_key=True)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("season.id"), primary_key=True)
    shirt_number: Mapped[int | None] = mapped_column(SmallInteger)


class Match(Base):
    __tablename__ = "match"
    __table_args__ = (
        UniqueConstraint("season_id", "stage", "home_team_id", "away_team_id"),
        CheckConstraint("home_team_id <> away_team_id", name="distinct_teams"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("season.id"))
    home_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("team.id"), index=True)
    away_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("team.id"), index=True)
    venue_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("venue.id"))
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    original_kickoff_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[MatchStatus] = mapped_column(_enum(MatchStatus, "match_status"))
    home_score: Mapped[int | None] = mapped_column(SmallInteger)
    away_score: Mapped[int | None] = mapped_column(SmallInteger)
    decided_by: Mapped[DecidedBy | None] = mapped_column(_enum(DecidedBy, "decided_by"))
    home_pens: Mapped[int | None] = mapped_column(SmallInteger)
    away_pens: Mapped[int | None] = mapped_column(SmallInteger)
    stage: Mapped[Stage] = mapped_column(_enum(Stage, "stage"))
    matchday: Mapped[int | None] = mapped_column(SmallInteger)
    round_label: Mapped[str] = mapped_column(String(128))


class Goal(Base):
    __tablename__ = "goal"
    __table_args__ = (UniqueConstraint("match_id", "ordinal"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(SmallInteger)
    side: Mapped[Side] = mapped_column(_enum(Side, "side"))
    scorer_player_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("player.id"))
    scorer_name: Mapped[str | None] = mapped_column(String(128))
    minute: Mapped[int | None] = mapped_column(SmallInteger)
    added_minute: Mapped[int | None] = mapped_column(SmallInteger)
    is_own_goal: Mapped[bool] = mapped_column(default=False)
    is_penalty: Mapped[bool] = mapped_column(default=False)


class ExternalRef(Base):
    """Maps a canonical entity UUID to its identifier in an external source."""

    __tablename__ = "external_ref"
    __table_args__ = (UniqueConstraint("entity_type", "source", "source_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    entity_type: Mapped[EntityType] = mapped_column(_enum(EntityType, "entity_type"))
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    source: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(256))

