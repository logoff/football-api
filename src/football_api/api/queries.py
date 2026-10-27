"""Reads shared by the REST and GraphQL APIs: filters, ordering, keyset paging and derived values.

Functions return ORM rows; each API turns them into its own response shapes, so both list the
same items in the same order and page them with the same cursors.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Select, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from football_api.api.pagination import apply_keyset, encode_cursor
from football_api.domain.enums import (
    CompetitionFormat,
    Coverage,
    LineupRole,
    Side,
    Stage,
    TeamKind,
    VerificationAspect,
    VerificationReference,
    VerificationStatus,
)
from football_api.infra.models import (
    Card,
    Competition,
    Goal,
    LineupEntry,
    Match,
    MatchVerification,
    Player,
    PlayerTeamSeason,
    Season,
    StandingVerification,
    Substitution,
    Team,
    TeamSeason,
    Venue,
)

type MatchRow = tuple[Match, Season]


@dataclass(frozen=True)
class Listing[R]:
    items: list[R]
    cursors: list[str]  # each item's own cursor: listing after it continues with the next item
    next_cursor: str | None  # the last item's cursor when more items follow


def _listing[R](rows: Sequence[R], limit: int, key: Callable[[R], Sequence[object]]) -> Listing[R]:
    items = list(rows[:limit])
    cursors = [encode_cursor(key(r)) for r in items]
    return Listing(items, cursors, cursors[-1] if len(rows) > limit else None)


# --- catalog -----------------------------------------------------------------------


async def competitions(
    session: AsyncSession, *, format: CompetitionFormat | None, limit: int, cursor: str | None
) -> Listing[Competition]:
    stmt = select(Competition)
    if format:
        stmt = stmt.where(Competition.format == format)
    rows = (await session.scalars(apply_keyset(stmt, [Competition.name, Competition.id], limit, cursor))).all()
    return _listing(rows, limit, lambda c: (c.name, c.id))


async def seasons(
    session: AsyncSession, *, competition_id: uuid.UUID | None, limit: int, cursor: str | None
) -> Listing[Season]:
    stmt = select(Season)
    if competition_id:
        stmt = stmt.where(Season.competition_id == competition_id)
    rows = (await session.scalars(apply_keyset(stmt, [Season.id], limit, cursor))).all()
    return _listing(rows, limit, lambda s: (s.id,))


async def teams(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID | None,
    season_id: uuid.UUID | None,
    kind: TeamKind | None,
    limit: int,
    cursor: str | None,
) -> Listing[Team]:
    stmt = select(Team)
    if kind:
        stmt = stmt.where(Team.kind == kind)
    if competition_id or season_id:
        participation = select(TeamSeason.team_id).join(Season, Season.id == TeamSeason.season_id)
        if competition_id:
            participation = participation.where(Season.competition_id == competition_id)
        if season_id:
            participation = participation.where(Season.id == season_id)
        stmt = stmt.where(Team.id.in_(participation))
    rows = (await session.scalars(apply_keyset(stmt, [Team.name, Team.id], limit, cursor))).all()
    return _listing(rows, limit, lambda t: (t.name, t.id))


async def team_seasons(session: AsyncSession, team_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[Season]]:
    """The seasons each team took part in, by season ID."""
    rows = await session.execute(
        select(TeamSeason.team_id, Season)
        .join(Season, Season.id == TeamSeason.season_id)
        .where(TeamSeason.team_id.in_(team_ids))
        .order_by(Season.id)
    )
    out: dict[uuid.UUID, list[Season]] = {}
    for team_id, season in rows:
        out.setdefault(team_id, []).append(season)
    return out


async def players(
    session: AsyncSession,
    *,
    team_id: uuid.UUID | None,
    season_id: uuid.UUID | None,
    competition_id: uuid.UUID | None,
    limit: int,
    cursor: str | None,
) -> Listing[Player]:
    stmt = select(Player)
    if team_id or season_id or competition_id:
        membership = select(PlayerTeamSeason.player_id).join(Season, Season.id == PlayerTeamSeason.season_id)
        if team_id:
            membership = membership.where(PlayerTeamSeason.team_id == team_id)
        if season_id:
            membership = membership.where(PlayerTeamSeason.season_id == season_id)
        if competition_id:
            membership = membership.where(Season.competition_id == competition_id)
        stmt = stmt.where(Player.id.in_(membership))
    rows = (await session.scalars(apply_keyset(stmt, [Player.display_name, Player.id], limit, cursor))).all()
    return _listing(rows, limit, lambda p: (p.display_name, p.id))


async def squad_coverage(session: AsyncSession, season_id: uuid.UUID) -> Coverage:
    """A team-season squad's coverage: the season's `players` coverage, `none` for an unknown season."""
    season = await session.get(Season, season_id)
    return season.players_coverage if season else Coverage.NONE


async def venues(session: AsyncSession, *, limit: int, cursor: str | None) -> Listing[Venue]:
    rows = (await session.scalars(apply_keyset(select(Venue), [Venue.name, Venue.id], limit, cursor))).all()
    return _listing(rows, limit, lambda v: (v.name, v.id))


async def standing_checks(
    session: AsyncSession, season_id: uuid.UUID
) -> dict[tuple[uuid.UUID, Stage, int, str], StandingVerification]:
    """Each standings row's check against the reference, by (team, stage, phase, group or "")."""
    rows = await session.scalars(
        select(StandingVerification).where(
            StandingVerification.season_id == season_id,
            StandingVerification.reference == VerificationReference.WIKIPEDIA,
        )
    )
    return {(v.team_id, v.stage, v.phase, v.group_name): v for v in rows}


# --- matches -----------------------------------------------------------------------


def _match_select() -> Select[Match, Season]:
    return select(Match, Season).join(Season, Season.id == Match.season_id)


async def matches(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID | None = None,
    season_id: uuid.UUID | None = None,
    team_id: uuid.UUID | None = None,
    stage: Stage | None = None,
    from_: date | None = None,
    to: date | None = None,
    verification: VerificationStatus | None = None,
    events_verification: VerificationStatus | None = None,
    limit: int,
    cursor: str | None,
) -> Listing[MatchRow]:
    stmt = _match_select()
    if competition_id:
        stmt = stmt.where(Season.competition_id == competition_id)
    if season_id:
        stmt = stmt.where(Match.season_id == season_id)
    if stage:
        stmt = stmt.where(Match.stage == stage)
    if team_id:
        stmt = stmt.where(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    if from_:
        stmt = stmt.where(Match.kickoff_utc >= datetime.combine(from_, time(0), tzinfo=UTC))
    if to:
        stmt = stmt.where(Match.kickoff_utc < datetime.combine(to + timedelta(days=1), time(0), tzinfo=UTC))
    for aspect, status in ((VerificationAspect.RESULT, verification), (VerificationAspect.EVENTS, events_verification)):
        if status:
            stmt = stmt.where(
                exists().where(
                    MatchVerification.match_id == Match.id,
                    MatchVerification.reference == VerificationReference.WIKIPEDIA,
                    MatchVerification.aspect == aspect,
                    MatchVerification.status == status,
                )
            )
    rows = (await session.execute(apply_keyset(stmt, [Match.kickoff_utc, Match.id], limit, cursor))).all()
    return _listing(rows, limit, lambda r: (r[0].kickoff_utc, r[0].id))


async def match(session: AsyncSession, id: uuid.UUID) -> MatchRow | None:
    return (await session.execute(_match_select().where(Match.id == id))).first()


async def verifications(
    session: AsyncSession, match_ids: Sequence[uuid.UUID]
) -> dict[tuple[uuid.UUID, VerificationAspect], MatchVerification]:
    """Each match's result and events checks against the reference, by (match, aspect)."""
    rows = await session.scalars(
        select(MatchVerification).where(
            MatchVerification.match_id.in_(match_ids),
            MatchVerification.reference == VerificationReference.WIKIPEDIA,
        )
    )
    return {(v.match_id, v.aspect): v for v in rows}


async def goals(session: AsyncSession, match_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[tuple[Goal, str | None]]]:
    """Each match's goals in source order, with the resolved scorer's display name."""
    rows = await session.execute(
        select(Goal, Player.display_name)
        .outerjoin(Player, Player.id == Goal.scorer_player_id)
        .where(Goal.match_id.in_(match_ids))
        .order_by(Goal.match_id, Goal.ordinal)
    )
    out: dict[uuid.UUID, list[tuple[Goal, str | None]]] = {}
    for goal, name in rows:
        out.setdefault(goal.match_id, []).append((goal, name))
    return out


def formation(entries: Sequence[LineupEntry]) -> str | None:
    """Starters per source line group after the first (the goalkeeper), joined by `-`; null for one group."""
    lines = [e.line_index for e in entries if e.role is LineupRole.STARTER and e.line_index is not None]
    if not lines or max(lines) < 2:
        return None
    return "-".join(str(lines.count(i)) for i in range(2, max(lines) + 1))


async def lineup_entries(
    session: AsyncSession, match_ids: Sequence[uuid.UUID]
) -> dict[tuple[uuid.UUID, Side], list[LineupEntry]]:
    """Each match side's line-up in source order: starters, then the substitutes who came on."""
    rows = await session.scalars(
        select(LineupEntry).where(LineupEntry.match_id.in_(match_ids)).order_by(LineupEntry.side, LineupEntry.ordinal)
    )
    out: dict[tuple[uuid.UUID, Side], list[LineupEntry]] = {}
    for e in rows:
        out.setdefault((e.match_id, e.side), []).append(e)
    return out


def _when(row: Substitution | Card) -> tuple[int, int, bool, int]:
    return row.minute, row.added_minute or 0, row.side is Side.AWAY, row.ordinal


async def substitutions(session: AsyncSession, match_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[Substitution]]:
    """Each match's substitutions by minute, then home before away, then source order."""
    rows = await session.scalars(select(Substitution).where(Substitution.match_id.in_(match_ids)))
    out: dict[uuid.UUID, list[Substitution]] = {}
    for s in sorted(rows, key=_when):
        out.setdefault(s.match_id, []).append(s)
    return out


async def cards(session: AsyncSession, match_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[Card]]:
    """Each match's cards by minute, then home before away, then source order."""
    rows = await session.scalars(select(Card).where(Card.match_id.in_(match_ids)))
    out: dict[uuid.UUID, list[Card]] = {}
    for c in sorted(rows, key=_when):
        out.setdefault(c.match_id, []).append(c)
    return out


# --- lookups by ID -----------------------------------------------------------------


async def by_id[M: (Competition, Season, Team, Player, Venue)](
    session: AsyncSession, model: type[M], ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, M]:
    if not ids:
        return {}
    return {row.id: row for row in await session.scalars(select(model).where(model.id.in_(ids)))}
