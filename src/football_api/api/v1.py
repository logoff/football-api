"""`/v1` routes. Every identifier, in paths and in filters, is a UUID."""

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from football_api.api.errors import ERROR_RESPONSES, ApiError, not_found
from football_api.api.pagination import DEFAULT_LIMIT, Cursor, Limit, apply_keyset, encode_cursor
from football_api.api.schemas import (
    CompetitionOut,
    GoalOut,
    GoalPlayerRef,
    MatchCoverage,
    MatchOut,
    Page,
    PlayerCoverage,
    PlayerOut,
    PlayerPage,
    SeasonCoverage,
    SeasonOut,
    TeamOut,
    TeamSeasonOut,
    VenueOut,
)
from football_api.domain.enums import Coverage, Stage, TeamKind
from football_api.infra.db import session_dependency
from football_api.infra.models import (
    Competition,
    Goal,
    Match,
    Player,
    PlayerTeamSeason,
    Season,
    Team,
    TeamSeason,
    Venue,
)

router = APIRouter(prefix="/v1", responses=ERROR_RESPONSES)
Session = Annotated[AsyncSession, Depends(session_dependency)]

CompetitionId = Annotated[uuid.UUID | None, Query(description="Only this competition")]
SeasonId = Annotated[uuid.UUID | None, Query(description="Only this season")]
TeamId = Annotated[uuid.UUID | None, Query(description="Only this team")]
Expand = Annotated[str | None, Query(description="Comma-separated related resources to embed")]


def parse_expand(raw: str | None, allowed: set[str]) -> set[str]:
    if not raw:
        return set()
    wanted = {part.strip() for part in raw.split(",") if part.strip()}
    unknown = wanted - allowed
    if unknown:
        raise ApiError(
            422,
            "invalid_expand",
            f"Unknown expand value(s): {', '.join(sorted(unknown))}",
            {"allowed": sorted(allowed)},
        )
    return wanted


def page_cursor[R](rows: Sequence[R], limit: int, key: Callable[[R], Sequence[object]]) -> str | None:
    return encode_cursor(key(rows[limit - 1])) if len(rows) > limit else None


# --- competitions ------------------------------------------------------------------


@router.get("/competitions", tags=["catalog"], summary="List competitions")
async def list_competitions(session: Session, limit: Limit = DEFAULT_LIMIT, cursor: Cursor = None) -> Page[CompetitionOut]:
    keys = [Competition.name, Competition.id]
    rows = (await session.scalars(apply_keyset(select(Competition), keys, limit, cursor))).all()
    return Page(
        data=[CompetitionOut.model_validate(c) for c in rows[:limit]],
        next_cursor=page_cursor(rows, limit, lambda c: (c.name, c.id)),
    )


@router.get("/competitions/{id}", tags=["catalog"], summary="Get a competition")
async def get_competition(session: Session, id: uuid.UUID) -> CompetitionOut:
    comp = await session.get(Competition, id)
    if comp is None:
        raise not_found("competition", id)
    return CompetitionOut.model_validate(comp)


# --- seasons -----------------------------------------------------------------------


def _season_out(season: Season) -> SeasonOut:
    return SeasonOut(
        id=season.id,
        competition_id=season.competition_id,
        label=season.label,
        starts_on=season.starts_on,
        ends_on=season.ends_on,
        status=season.status,
        coverage=SeasonCoverage(scorers=season.scorers_coverage, players=season.players_coverage),
    )


@router.get("/seasons", tags=["catalog"], summary="List seasons")
async def list_seasons(
    session: Session, competition_id: CompetitionId = None, limit: Limit = DEFAULT_LIMIT, cursor: Cursor = None
) -> Page[SeasonOut]:
    stmt = select(Season)
    if competition_id:
        stmt = stmt.where(Season.competition_id == competition_id)
    rows = (await session.scalars(apply_keyset(stmt, [Season.id], limit, cursor))).all()
    return Page(data=[_season_out(s) for s in rows[:limit]], next_cursor=page_cursor(rows, limit, lambda s: (s.id,)))


@router.get("/seasons/{id}", tags=["catalog"], summary="Get a season")
async def get_season(session: Session, id: uuid.UUID) -> SeasonOut:
    season = await session.get(Season, id)
    if season is None:
        raise not_found("season", id)
    return _season_out(season)


# --- teams -------------------------------------------------------------------------


async def _team_seasons(session: AsyncSession, team_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[TeamSeasonOut]]:
    rows = await session.execute(
        select(TeamSeason.team_id, Season.id, Season.competition_id, Season.label)
        .join(Season, Season.id == TeamSeason.season_id)
        .where(TeamSeason.team_id.in_(team_ids))
        .order_by(Season.id)
    )
    out: dict[uuid.UUID, list[TeamSeasonOut]] = {}
    for team_id, season_id, competition_id, label in rows:
        out.setdefault(team_id, []).append(TeamSeasonOut(season_id=season_id, competition_id=competition_id, label=label))
    return out


@router.get("/teams", tags=["catalog"], summary="List teams")
async def list_teams(
    session: Session,
    competition_id: CompetitionId = None,
    season_id: SeasonId = None,
    kind: TeamKind | None = None,
    expand: Expand = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
) -> Page[TeamOut]:
    expands = parse_expand(expand, {"seasons"})
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
    teams = [TeamOut.model_validate(t) for t in rows[:limit]]
    if "seasons" in expands:
        seasons = await _team_seasons(session, [t.id for t in teams])
        for t in teams:
            t.seasons = seasons.get(t.id, [])
    return Page(data=teams, next_cursor=page_cursor(rows, limit, lambda t: (t.name, t.id)))


@router.get("/teams/{id}", tags=["catalog"], summary="Get a team")
async def get_team(session: Session, id: uuid.UUID, expand: Expand = None) -> TeamOut:
    expands = parse_expand(expand, {"seasons"})
    team = await session.get(Team, id)
    if team is None:
        raise not_found("team", id)
    out = TeamOut.model_validate(team)
    if "seasons" in expands:
        out.seasons = (await _team_seasons(session, [team.id])).get(team.id, [])
    return out


# --- players -----------------------------------------------------------------------


@router.get("/players", tags=["catalog"], summary="List players")
async def list_players(
    session: Session,
    team_id: TeamId = None,
    season_id: SeasonId = None,
    competition_id: CompetitionId = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
) -> PlayerPage:
    """Players exist only where openfootball publishes squads; see `coverage`."""
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

    coverage: PlayerCoverage | None = None
    if team_id and season_id:
        season = await session.get(Season, season_id)
        coverage = PlayerCoverage(players=season.players_coverage if season else Coverage.NONE)

    return PlayerPage(
        data=[PlayerOut.model_validate(p) for p in rows[:limit]],
        next_cursor=page_cursor(rows, limit, lambda p: (p.display_name, p.id)),
        coverage=coverage,
    )


@router.get("/players/{id}", tags=["catalog"], summary="Get a player")
async def get_player(session: Session, id: uuid.UUID) -> PlayerOut:
    player = await session.get(Player, id)
    if player is None:
        raise not_found("player", id)
    return PlayerOut.model_validate(player)


# --- venues ------------------------------------------------------------------------


@router.get("/venues", tags=["catalog"], summary="List venues")
async def list_venues(session: Session, limit: Limit = DEFAULT_LIMIT, cursor: Cursor = None) -> Page[VenueOut]:
    rows = (await session.scalars(apply_keyset(select(Venue), [Venue.name, Venue.id], limit, cursor))).all()
    return Page(
        data=[VenueOut.model_validate(v) for v in rows[:limit]],
        next_cursor=page_cursor(rows, limit, lambda v: (v.name, v.id)),
    )


@router.get("/venues/{id}", tags=["catalog"], summary="Get a venue")
async def get_venue(session: Session, id: uuid.UUID) -> VenueOut:
    venue = await session.get(Venue, id)
    if venue is None:
        raise not_found("venue", id)
    return VenueOut.model_validate(venue)


# --- matches -----------------------------------------------------------------------

MATCH_EXPANDS = {"teams", "venue", "scorers"}
type MatchRow = tuple[Match, uuid.UUID, Coverage]


def _match_select() -> Select[Match, uuid.UUID, Coverage]:
    return select(Match, Season.competition_id, Season.scorers_coverage).join(Season, Season.id == Match.season_id)


async def _matches_out(session: AsyncSession, rows: Sequence[MatchRow], expands: set[str]) -> list[MatchOut]:
    matches = [r[0] for r in rows]
    teams: dict[uuid.UUID, TeamOut] = {}
    venues: dict[uuid.UUID, VenueOut] = {}
    goals: dict[uuid.UUID, list[GoalOut]] = {}
    if "teams" in expands:
        ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
        teams = {t.id: TeamOut.model_validate(t) for t in await session.scalars(select(Team).where(Team.id.in_(ids)))}
    if "venue" in expands:
        ids = {m.venue_id for m in matches if m.venue_id}
        venues = {v.id: VenueOut.model_validate(v) for v in await session.scalars(select(Venue).where(Venue.id.in_(ids)))}
    if "scorers" in expands:
        goal_rows = await session.execute(
            select(Goal, Player.display_name)
            .outerjoin(Player, Player.id == Goal.scorer_player_id)
            .where(Goal.match_id.in_([m.id for m in matches]))
            .order_by(Goal.match_id, Goal.ordinal)
        )
        for goal, player_name in goal_rows:
            player = GoalPlayerRef(id=goal.scorer_player_id, display_name=player_name) if goal.scorer_player_id and player_name else None
            goals.setdefault(goal.match_id, []).append(
                GoalOut(
                    ordinal=goal.ordinal,
                    side=goal.side,
                    player=player,
                    name=player_name or goal.scorer_name or "",
                    minute=goal.minute,
                    added_minute=goal.added_minute,
                    is_penalty=goal.is_penalty,
                    is_own_goal=goal.is_own_goal,
                )
            )

    out: list[MatchOut] = []
    for m, competition_id, scorers_coverage in rows:
        item = MatchOut(
            id=m.id,
            competition_id=competition_id,
            season_id=m.season_id,
            stage=m.stage,
            matchday=m.matchday,
            round_label=m.round_label,
            kickoff_utc=m.kickoff_utc,
            original_kickoff_utc=m.original_kickoff_utc,
            status=m.status,
            home_team_id=m.home_team_id,
            away_team_id=m.away_team_id,
            venue_id=m.venue_id,
            home_score=m.home_score,
            away_score=m.away_score,
            decided_by=m.decided_by,
            home_pens=m.home_pens,
            away_pens=m.away_pens,
            coverage=MatchCoverage(scorers=scorers_coverage),
        )
        if "teams" in expands:
            item.home_team, item.away_team = teams.get(m.home_team_id), teams.get(m.away_team_id)
        if "venue" in expands:
            item.venue = venues.get(m.venue_id) if m.venue_id else None
        if "scorers" in expands:
            item.scorers = goals.get(m.id, [])
        out.append(item)
    return out


MatchExpand = Annotated[str | None, Query(description="Comma-separated: teams, venue, scorers")]


@router.get("/matches", tags=["matches"], summary="List matches")
async def list_matches(
    session: Session,
    competition_id: CompetitionId = None,
    season_id: SeasonId = None,
    team_id: Annotated[uuid.UUID | None, Query(description="Matches where this team plays home or away")] = None,
    stage: Stage | None = None,
    from_: Annotated[date | None, Query(alias="from", description="Kickoff on or after this UTC date")] = None,
    to: Annotated[date | None, Query(description="Kickoff on or before this UTC date (inclusive)")] = None,
    expand: MatchExpand = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
) -> Page[MatchOut]:
    expands = parse_expand(expand, MATCH_EXPANDS)
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
    rows: Sequence[MatchRow] = (
        await session.execute(apply_keyset(stmt, [Match.kickoff_utc, Match.id], limit, cursor))
    ).all()
    return Page(
        data=await _matches_out(session, rows[:limit], expands),
        next_cursor=page_cursor(rows, limit, lambda r: (r[0].kickoff_utc, r[0].id)),
    )


@router.get("/matches/{id}", tags=["matches"], summary="Get a match")
async def get_match(session: Session, id: uuid.UUID, expand: MatchExpand = None) -> MatchOut:
    expands = parse_expand(expand, MATCH_EXPANDS)
    row = (await session.execute(_match_select().where(Match.id == id))).first()
    if row is None:
        raise not_found("match", id)
    return (await _matches_out(session, [row], expands))[0]
