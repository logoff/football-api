"""`/v1` routes. Every identifier, in paths and in filters, is a UUID."""

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from football_api.api import queries
from football_api.api.errors import ERROR_RESPONSES, ApiError, not_found
from football_api.api.pagination import DEFAULT_LIMIT, Cursor, Limit
from football_api.api.queries import MatchRow
from football_api.api.schemas import (
    CardOut,
    CompetitionOut,
    GoalOut,
    LineupEntryOut,
    LineupOut,
    LineupsOut,
    MatchCoverage,
    MatchOut,
    MatchVerificationOut,
    Page,
    PlayerCoverage,
    PlayerOut,
    PlayerPage,
    PlayerRef,
    SeasonCoverage,
    SeasonOut,
    StandingAdjustmentOut,
    StandingRowOut,
    StandingsOut,
    StandingTableOut,
    SubstitutionOut,
    TeamOut,
    TeamSeasonOut,
    VenueOut,
)
from football_api.domain.enums import (
    CompetitionFormat,
    Side,
    Stage,
    TeamKind,
    VerificationAspect,
    VerificationStatus,
)
from football_api.infra.db import session_dependency
from football_api.infra.models import (
    Competition,
    LineupEntry,
    MatchVerification,
    Player,
    Season,
    StandingVerification,
    Team,
    Venue,
)
from football_api.season_tables import season_tables

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


def verification_out(v: MatchVerification | StandingVerification | None) -> MatchVerificationOut | None:
    return MatchVerificationOut(status=v.status, reference=v.reference, checked_at=v.checked_at) if v else None


# --- competitions ------------------------------------------------------------------


@router.get("/competitions", tags=["catalog"], summary="List competitions")
async def list_competitions(
    session: Session,
    format: Annotated[CompetitionFormat | None, Query(description="Only competitions of this format")] = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
) -> Page[CompetitionOut]:
    listing = await queries.competitions(session, format=format, limit=limit, cursor=cursor)
    return Page(data=[CompetitionOut.model_validate(c) for c in listing.items], next_cursor=listing.next_cursor)


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
        coverage=SeasonCoverage(
            scorers=season.scorers_coverage,
            players=season.players_coverage,
            lineups=season.lineups_coverage,
            substitutions=season.substitutions_coverage,
            cards=season.cards_coverage,
        ),
    )


@router.get("/seasons", tags=["catalog"], summary="List seasons")
async def list_seasons(
    session: Session, competition_id: CompetitionId = None, limit: Limit = DEFAULT_LIMIT, cursor: Cursor = None
) -> Page[SeasonOut]:
    listing = await queries.seasons(session, competition_id=competition_id, limit=limit, cursor=cursor)
    return Page(data=[_season_out(s) for s in listing.items], next_cursor=listing.next_cursor)


@router.get("/seasons/{id}", tags=["catalog"], summary="Get a season")
async def get_season(session: Session, id: uuid.UUID) -> SeasonOut:
    season = await session.get(Season, id)
    if season is None:
        raise not_found("season", id)
    return _season_out(season)


# --- standings ---------------------------------------------------------------------


AsOf = Annotated[date | None, Query(description="Tables as of this date (in the season's time zone); default: the latest results")]


@router.get("/seasons/{id}/standings", tags=["catalog"], summary="Get a season's standings")
async def get_standings(session: Session, id: uuid.UUID, as_of: AsOf = None, expand: Expand = None) -> StandingsOut:
    """League table, or one table per group, computed from the season's results with the
    competition's ranking rules and any curated point adjustments."""
    expands = parse_expand(expand, {"teams"})
    season = await session.get(Season, id)
    if season is None:
        raise not_found("season", id)
    tables = await season_tables(session, season, as_of)
    checks = {} if as_of is not None else await queries.standing_checks(session, season.id)
    team_out = (
        {
            t.id: TeamOut.model_validate(t)
            for t in (await queries.by_id(session, Team, list({r.team for t in tables for r in t.rows}))).values()
        }
        if "teams" in expands
        else {}
    )
    return StandingsOut(
        season_id=season.id,
        as_of=as_of,
        tables=[
            StandingTableOut(
                stage=t.key.stage,
                phase=t.key.phase,
                group=t.key.group,
                status=t.status,
                rows=[
                    StandingRowOut(
                        position=r.position,
                        team_id=r.team,
                        team=team_out.get(r.team),
                        played=r.played,
                        won=r.won,
                        drawn=r.drawn,
                        lost=r.lost,
                        goals_for=r.goals_for,
                        goals_against=r.goals_against,
                        goal_difference=r.goal_difference,
                        points=r.points,
                        adjustments=[
                            StandingAdjustmentOut(points=a.points, reason=a.reason, source=a.source)
                            for a in t.adjustments.get(r.team, [])
                        ],
                        tied=r.tied,
                        verification=verification_out(checks.get((r.team, t.key.stage, t.key.phase, t.key.group or "")))
                        if t.status == "final"
                        else None,
                    )
                    for r in t.rows
                ],
            )
            for t in tables
        ],
    )


# --- teams -------------------------------------------------------------------------


async def _team_seasons(session: AsyncSession, team_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[TeamSeasonOut]]:
    return {
        team_id: [TeamSeasonOut(season_id=s.id, competition_id=s.competition_id, label=s.label) for s in seasons]
        for team_id, seasons in (await queries.team_seasons(session, team_ids)).items()
    }


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
    listing = await queries.teams(
        session, competition_id=competition_id, season_id=season_id, kind=kind, limit=limit, cursor=cursor
    )
    teams = [TeamOut.model_validate(t) for t in listing.items]
    if "seasons" in expands:
        seasons = await _team_seasons(session, [t.id for t in teams])
        for t in teams:
            t.seasons = seasons.get(t.id, [])
    return Page(data=teams, next_cursor=listing.next_cursor)


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
    listing = await queries.players(
        session, team_id=team_id, season_id=season_id, competition_id=competition_id, limit=limit, cursor=cursor
    )
    coverage = (
        PlayerCoverage(players=await queries.squad_coverage(session, season_id)) if team_id and season_id else None
    )
    return PlayerPage(
        data=[PlayerOut.model_validate(p) for p in listing.items], next_cursor=listing.next_cursor, coverage=coverage
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
    listing = await queries.venues(session, limit=limit, cursor=cursor)
    return Page(data=[VenueOut.model_validate(v) for v in listing.items], next_cursor=listing.next_cursor)


@router.get("/venues/{id}", tags=["catalog"], summary="Get a venue")
async def get_venue(session: Session, id: uuid.UUID) -> VenueOut:
    venue = await session.get(Venue, id)
    if venue is None:
        raise not_found("venue", id)
    return VenueOut.model_validate(venue)


# --- matches -----------------------------------------------------------------------

MATCH_EXPANDS = {"teams", "venue", "scorers", "lineups", "substitutions", "cards"}


async def _matches_out(session: AsyncSession, rows: Sequence[MatchRow], expands: set[str]) -> list[MatchOut]:
    match_ids = [m.id for m, _ in rows]
    checks = await queries.verifications(session, match_ids)
    teams = (
        await queries.by_id(session, Team, list({i for m, _ in rows for i in (m.home_team_id, m.away_team_id)}))
        if "teams" in expands
        else {}
    )
    venues = (
        await queries.by_id(session, Venue, list({m.venue_id for m, _ in rows if m.venue_id})) if "venue" in expands else {}
    )
    goals = await queries.goals(session, match_ids) if "scorers" in expands else {}
    entries = await queries.lineup_entries(session, match_ids) if "lineups" in expands else {}
    subs = await queries.substitutions(session, match_ids) if "substitutions" in expands else {}
    cards = await queries.cards(session, match_ids) if "cards" in expands else {}
    players = await queries.by_id(
        session,
        Player,
        list(
            {e.player_id for es in entries.values() for e in es if e.player_id}
            | {i for ss in subs.values() for s in ss for i in (s.player_off_id, s.player_on_id) if i}
            | {c.player_id for cs in cards.values() for c in cs if c.player_id}
        ),
    )

    def ref(player_id: uuid.UUID | None) -> PlayerRef | None:
        p = players.get(player_id) if player_id else None
        return PlayerRef(id=p.id, display_name=p.display_name) if p else None

    def lineup(rows: list[LineupEntry]) -> LineupOut:
        return LineupOut(
            formation=queries.formation(rows),
            entries=[
                LineupEntryOut(
                    player=ref(e.player_id), name=e.player_name, role=e.role, line=e.line_index, is_captain=e.is_captain
                )
                for e in rows
            ],
        )

    out: list[MatchOut] = []
    for m, season in rows:
        item = MatchOut(
            id=m.id,
            competition_id=season.competition_id,
            season_id=m.season_id,
            stage=m.stage,
            matchday=m.matchday,
            occurrence=m.occurrence,
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
            awarded=m.awarded,
            referee=m.referee_name,
            attendance=m.attendance,
            coverage=MatchCoverage(
                scorers=season.scorers_coverage,
                lineups=season.lineups_coverage,
                substitutions=season.substitutions_coverage,
                cards=season.cards_coverage,
            ),
            verification=verification_out(checks.get((m.id, VerificationAspect.RESULT))),
            events_verification=verification_out(checks.get((m.id, VerificationAspect.EVENTS))),
        )
        if "teams" in expands:
            home, away = teams.get(m.home_team_id), teams.get(m.away_team_id)
            item.home_team = TeamOut.model_validate(home) if home else None
            item.away_team = TeamOut.model_validate(away) if away else None
        if "venue" in expands:
            venue = venues.get(m.venue_id) if m.venue_id else None
            item.venue = VenueOut.model_validate(venue) if venue else None
        if "scorers" in expands:
            item.scorers = [
                GoalOut(
                    ordinal=g.ordinal,
                    side=g.side,
                    player=PlayerRef(id=g.scorer_player_id, display_name=name) if g.scorer_player_id and name else None,
                    name=name or g.scorer_name or "",
                    minute=g.minute,
                    added_minute=g.added_minute,
                    is_penalty=g.is_penalty,
                    is_own_goal=g.is_own_goal,
                )
                for g, name in goals.get(m.id, [])
            ]
        if "lineups" in expands:
            item.lineups = LineupsOut(
                home=lineup(entries.get((m.id, Side.HOME), [])), away=lineup(entries.get((m.id, Side.AWAY), []))
            )
        if "substitutions" in expands:
            item.substitutions = [
                SubstitutionOut(
                    side=s.side, minute=s.minute, added_minute=s.added_minute,
                    player_off=ref(s.player_off_id), player_off_name=s.player_off_name,
                    player_on=ref(s.player_on_id), player_on_name=s.player_on_name,
                )
                for s in subs.get(m.id, [])
            ]
        if "cards" in expands:
            item.cards = [
                CardOut(
                    side=c.side, minute=c.minute, added_minute=c.added_minute, kind=c.kind,
                    player=ref(c.player_id), name=c.player_name,
                )
                for c in cards.get(m.id, [])
            ]
        out.append(item)
    return out


MatchExpand = Annotated[
    str | None, Query(description="Comma-separated: teams, venue, scorers, lineups, substitutions, cards")
]


@router.get("/matches", tags=["matches"], summary="List matches")
async def list_matches(
    session: Session,
    competition_id: CompetitionId = None,
    season_id: SeasonId = None,
    team_id: Annotated[uuid.UUID | None, Query(description="Matches where this team plays home or away")] = None,
    stage: Stage | None = None,
    from_: Annotated[date | None, Query(alias="from", description="Kickoff on or after this UTC date")] = None,
    to: Annotated[date | None, Query(description="Kickoff on or before this UTC date (inclusive)")] = None,
    verification: Annotated[
        VerificationStatus | None, Query(description="Only matches with this verification status")
    ] = None,
    events_verification: Annotated[
        VerificationStatus | None, Query(description="Only matches with this events verification status")
    ] = None,
    expand: MatchExpand = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
) -> Page[MatchOut]:
    expands = parse_expand(expand, MATCH_EXPANDS)
    listing = await queries.matches(
        session,
        competition_id=competition_id,
        season_id=season_id,
        team_id=team_id,
        stage=stage,
        from_=from_,
        to=to,
        verification=verification,
        events_verification=events_verification,
        limit=limit,
        cursor=cursor,
    )
    return Page(data=await _matches_out(session, listing.items, expands), next_cursor=listing.next_cursor)


@router.get("/matches/{id}", tags=["matches"], summary="Get a match")
async def get_match(session: Session, id: uuid.UUID, expand: MatchExpand = None) -> MatchOut:
    expands = parse_expand(expand, MATCH_EXPANDS)
    row = await queries.match(session, id)
    if row is None:
        raise not_found("match", id)
    return (await _matches_out(session, [row], expands))[0]
