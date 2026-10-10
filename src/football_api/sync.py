"""`just sync`: reconcile seeds, Wikidata and openfootball into the database.

Order: competitions and teams from `seeds/` → Wikidata check of seeded QIDs → one
transaction per competition-season for the openfootball data. Every write is an upsert
on a natural key (ingestion spec, "Idempotency"), so an unchanged re-run rewrites
identical values and creates nothing.
"""

import asyncio
import logging
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from football_api.domain.enums import Coverage, EntityType, MatchStatus, SeasonStatus, TeamKind
from football_api.infra.db import get_sessionmaker
from football_api.infra.models import (
    Competition,
    ExternalRef,
    Goal,
    Match,
    Player,
    PlayerTeamSeason,
    Season,
    Team,
    TeamSeason,
    Venue,
)
from football_api.infra.settings import get_settings
from football_api.ingestion.openfootball.json_reader import is_current, read_json
from football_api.ingestion.openfootball.names import fold, short_name_matches, split_capitalised
from football_api.ingestion.openfootball.squads import SquadPlayer, parse_more_squads, parse_per_team_squad
from football_api.ingestion.openfootball.text_parser import ParsedMatch, normalize_stage, parse_file
from football_api.ingestion.seeds import CompetitionSeed, TeamSeed, load_competitions, load_teams
from football_api.ingestion.sources import ensure_sources
from football_api.ingestion.wikidata import WikidataUnavailable, verify_qids

log = logging.getLogger("football_api.sync")

OPENFOOTBALL = "openfootball"
WIKIDATA = "wikidata"


class SyncError(Exception):
    pass


class UnknownTeamError(SyncError):
    def __init__(self, path: str, line_no: int, name: str) -> None:
        super().__init__(f"{path}:{line_no}: unknown team {name!r} — add it to seeds/teams.yaml")


async def ensure_ref(session: AsyncSession, entity_type: EntityType, entity_id: uuid.UUID, source: str, source_id: str) -> None:
    existing = await session.scalar(
        select(ExternalRef).where(
            ExternalRef.entity_type == entity_type,
            ExternalRef.source == source,
            ExternalRef.source_id == source_id,
        )
    )
    if existing is None:
        session.add(ExternalRef(entity_type=entity_type, entity_id=entity_id, source=source, source_id=source_id))
    elif existing.entity_id != entity_id:
        raise SyncError(f"{source}:{source_id} already maps to another {entity_type.value} ({existing.entity_id})")


async def lookup_ref(session: AsyncSession, entity_type: EntityType, source: str, source_id: str) -> uuid.UUID | None:
    return await session.scalar(
        select(ExternalRef.entity_id).where(
            ExternalRef.entity_type == entity_type,
            ExternalRef.source == source,
            ExternalRef.source_id == source_id,
        )
    )


# --- seeds -------------------------------------------------------------------------


async def upsert_competition(session: AsyncSession, seed: CompetitionSeed) -> Competition:
    """Match the competition through its Wikidata QID (its only identity), else create it."""
    comp_id = await lookup_ref(session, EntityType.COMPETITION, WIKIDATA, seed.wikidata)
    comp = await session.get(Competition, comp_id) if comp_id else None
    if comp is None:
        comp = Competition()
        session.add(comp)
    comp.name, comp.country, comp.team_kind, comp.scope = seed.name, seed.country, seed.team_kind, seed.scope
    await session.flush()
    await ensure_ref(session, EntityType.COMPETITION, comp.id, WIKIDATA, seed.wikidata)
    return comp


async def find_team(session: AsyncSession, seed: TeamSeed) -> Team | None:
    """Match a teams.yaml entry to its row through its external refs (aliases, QID).

    Entries carry no key of our own, so editing a name never creates a second team.
    """
    refs = [(OPENFOOTBALL, alias) for alias in seed.openfootball]
    if seed.wikidata:
        refs.append((WIKIDATA, seed.wikidata))
    known = {team_id for source, source_id in refs if (team_id := await lookup_ref(session, EntityType.TEAM, source, source_id))}
    if len(known) > 1:
        raise SyncError(f"teams.yaml entry {seed.name!r} matches {len(known)} existing teams; merge them by hand")
    return await session.get(Team, known.pop()) if known else None


async def sync_teams(session: AsyncSession, seeds: list[TeamSeed]) -> None:
    for seed in seeds:
        team = await find_team(session, seed)
        if team is None:
            team = Team()
            session.add(team)
        team.name, team.country, team.kind = seed.name, seed.country, seed.kind
        await session.flush()
        for alias in seed.openfootball:
            await ensure_ref(session, EntityType.TEAM, team.id, OPENFOOTBALL, alias)
        if seed.wikidata:
            await ensure_ref(session, EntityType.TEAM, team.id, WIKIDATA, seed.wikidata)


async def verify_wikidata(competitions: list[CompetitionSeed], teams: list[TeamSeed]) -> None:
    """Warn about seeded QIDs that no longer exist. Identity never depends on this step.

    If the endpoint is down the check is skipped.
    """
    wanted = {c.wikidata: f"competition {c.name}" for c in competitions}
    wanted |= {t.wikidata: f"team {t.name}" for t in teams if t.wikidata}
    try:
        confirmed = await verify_qids(sorted(wanted), endpoint=get_settings().wikidata_endpoint)
    except WikidataUnavailable as exc:
        log.error("Wikidata check skipped: %s", exc)
        return
    for qid, what in sorted(wanted.items()):
        if qid not in confirmed:
            log.warning("%s: Wikidata has no item %s (deleted or merged?)", what, qid)


# --- openfootball --------------------------------------------------------------------


@dataclass
class SeasonContext:
    seed: CompetitionSeed
    season: Season
    sources: Path
    scorer_names_capitalised: bool
    squads: dict[uuid.UUID, list[tuple[Player, str]]]  # team_id → [(player, display)]


async def resolve_team(session: AsyncSession, path: str, line_no: int, name: str) -> uuid.UUID:
    team_id = await lookup_ref(session, EntityType.TEAM, OPENFOOTBALL, name)
    if team_id is None:
        raise UnknownTeamError(path, line_no, name)
    return team_id


def kickoff_utc(m: ParsedMatch, tz: str, path: str) -> datetime:
    """Line offset first, then the file's configured zone (design.md, "Kickoff time zones")."""
    local = datetime.combine(m.day, m.kickoff or time(0, 0))
    if m.utc_offset is not None:
        return (local - m.utc_offset).replace(tzinfo=UTC)
    if tz == "inline":
        if m.kickoff is None:  # a postponed fixture with no time: keep the date, midnight UTC
            return local.replace(tzinfo=UTC)
        raise SyncError(f"{path}:{m.line_no}: no UTC offset on the line and the file's tz is `inline`")
    return local.replace(tzinfo=ZoneInfo(tz)).astimezone(UTC)


async def upsert_venue(session: AsyncSession, name: str | None, city: str | None) -> uuid.UUID | None:
    if not name:
        return None
    venue = await session.scalar(select(Venue).where(Venue.name == name, Venue.city.is_not_distinct_from(city)))
    if venue is None:
        venue = Venue(name=name, city=city)
        session.add(venue)
        await session.flush()
    await ensure_ref(session, EntityType.VENUE, venue.id, OPENFOOTBALL, f"{name}, {city}" if city else name)
    return venue.id


async def sync_squads(session: AsyncSession, ctx: SeasonContext) -> None:
    squad_src = ctx.seed.season.squads
    if squad_src is None:
        return
    players: list[SquadPlayer] = []
    for pattern in squad_src.files:
        paths = sorted(ctx.sources.glob(pattern))
        if not paths:
            raise SyncError(f"squad pattern matched no files: {pattern}")
        for path in paths:
            text = path.read_text(encoding="utf-8")
            players += parse_more_squads(text) if squad_src.style == "more" else parse_per_team_squad(text)

    existing_rows = await session.execute(
        select(PlayerTeamSeason.team_id, Player)
        .join(Player, Player.id == PlayerTeamSeason.player_id)
        .where(PlayerTeamSeason.season_id == ctx.season.id)
    )
    existing: dict[tuple[uuid.UUID, str], Player] = {(team_id, p.display_name): p for team_id, p in existing_rows}

    for sp in players:
        team_id = await resolve_team(session, squad_src.files[0], 0, sp.team)
        player = existing.get((team_id, sp.name.display))
        if player is None:
            player = Player(display_name=sp.name.display)
            session.add(player)
            await session.flush()
            session.add(PlayerTeamSeason(player_id=player.id, team_id=team_id, season_id=ctx.season.id))
            existing[(team_id, sp.name.display)] = player
        player.given_name, player.family_name = sp.name.given, sp.name.family
        if ctx.seed.team_kind is TeamKind.NATIONAL:
            player.nationality = await session.scalar(select(Team.country).where(Team.id == team_id))
        player.birth_year, player.dob, player.position = sp.birth_year, sp.dob, sp.position
        pts = await session.get(PlayerTeamSeason, (player.id, team_id, ctx.season.id))
        if pts is not None:
            pts.shirt_number = sp.shirt_number
        await ensure_ref(
            session, EntityType.PLAYER, player.id, OPENFOOTBALL, f"{ctx.seed.season.file}#{sp.team}#{sp.name.display}"
        )
        ctx.squads.setdefault(team_id, []).append((player, sp.name.display))
    await session.flush()


def resolve_scorer(name: str, candidates: list[tuple[Player, str]]) -> Player | None:
    exact = [p for p, display in candidates if fold(display) == fold(name)]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None
    partial = [p for p, display in candidates if short_name_matches(name, display)]
    return partial[0] if len(partial) == 1 else None


async def sync_goals(session: AsyncSession, ctx: SeasonContext, match: Match, parsed: ParsedMatch) -> None:
    candidates = ctx.squads.get(match.home_team_id, []) + ctx.squads.get(match.away_team_id, [])
    current = {g.ordinal: g for g in await session.scalars(select(Goal).where(Goal.match_id == match.id))}
    for ordinal, pg in enumerate(parsed.goals, 1):
        goal = current.get(ordinal)
        if goal is None:
            goal = Goal(match_id=match.id, ordinal=ordinal)
            session.add(goal)
        scorer = resolve_scorer(pg.name, candidates)
        source_name = split_capitalised(pg.name).display if ctx.scorer_names_capitalised else pg.name
        goal.side = pg.side
        goal.scorer_player_id = scorer.id if scorer else None
        goal.scorer_name = None if scorer else source_name
        goal.minute, goal.added_minute = pg.minute, pg.added_minute
        goal.is_penalty, goal.is_own_goal = pg.is_penalty, pg.is_own_goal
    await session.execute(delete(Goal).where(Goal.match_id == match.id, Goal.ordinal > len(parsed.goals)))


async def sync_match(session: AsyncSession, ctx: SeasonContext, m: ParsedMatch, path: str) -> None:
    home_id = await resolve_team(session, path, m.line_no, m.home)
    away_id = await resolve_team(session, path, m.line_no, m.away)
    stage, matchday = normalize_stage(m.round_label)
    kickoff = kickoff_utc(m, ctx.seed.season.tz, path)
    match = await session.scalar(
        select(Match).where(
            Match.season_id == ctx.season.id,
            Match.stage == stage,
            Match.home_team_id == home_id,
            Match.away_team_id == away_id,
        )
    )
    if match is None:
        match = Match(season_id=ctx.season.id, stage=stage, home_team_id=home_id, away_team_id=away_id, kickoff_utc=kickoff)
        session.add(match)
    elif match.kickoff_utc != kickoff and match.original_kickoff_utc is None:
        match.original_kickoff_utc = match.kickoff_utc
    match.kickoff_utc = kickoff
    match.matchday, match.round_label, match.status = matchday, m.round_label, m.status
    match.venue_id = await upsert_venue(session, m.venue_name, m.venue_city)
    score = m.score
    match.home_score = score.home if score else None
    match.away_score = score.away if score else None
    match.decided_by = score.decided_by if score else None
    match.home_pens = score.home_pens if score else None
    match.away_pens = score.away_pens if score else None
    await session.flush()
    await ensure_ref(session, EntityType.MATCH, match.id, OPENFOOTBALL, f"{path}#{stage.value}#{m.home}#{m.away}")
    if m.goals_listed:
        await sync_goals(session, ctx, match, m)


def read_matches(seed: CompetitionSeed, sources: Path) -> tuple[list[ParsedMatch], str]:
    s = seed.season
    text_matches = parse_file(sources / s.file, start_year=s.start_year, display_path=s.file)
    if s.json_file:
        if not (sources / s.json_file).exists():
            log.info("%s: JSON mirror %s missing; using text file", seed.name, s.json_file)
            return text_matches, s.file
        json_matches = read_json(sources / s.json_file)
        if is_current(json_matches, text_matches):
            return json_matches, s.json_file
        log.info("%s: JSON mirror not current; using text file", seed.name)
    return text_matches, s.file


async def sync_season(session: AsyncSession, seed: CompetitionSeed, sources: Path) -> int:
    comp = await upsert_competition(session, seed)
    matches, path = read_matches(seed, sources)
    season = await session.scalar(select(Season).where(Season.competition_id == comp.id, Season.label == seed.season.label))
    if season is None:
        season = Season(competition_id=comp.id, label=seed.season.label)
        session.add(season)
    days: list[date] = [m.day for m in matches]
    season.starts_on, season.ends_on = min(days), max(days)
    season.status = (
        SeasonStatus.COMPLETED
        if all(m.status is not MatchStatus.SCHEDULED for m in matches)
        else SeasonStatus.IN_PROGRESS
    )
    season.scorers_coverage = Coverage.FULL if any(m.goals_listed for m in matches) else Coverage.NONE
    season.players_coverage = Coverage.FULL if seed.season.squads else Coverage.NONE
    await session.flush()
    await ensure_ref(session, EntityType.SEASON, season.id, OPENFOOTBALL, seed.season.file)

    team_ids: set[uuid.UUID] = set()
    for m in matches:
        team_ids.add(await resolve_team(session, path, m.line_no, m.home))
        team_ids.add(await resolve_team(session, path, m.line_no, m.away))
    for team_id in team_ids:
        if await session.get(TeamSeason, (team_id, season.id)) is None:
            session.add(TeamSeason(team_id=team_id, season_id=season.id))

    squads_style = seed.season.squads.style if seed.season.squads else None
    ctx = SeasonContext(seed, season, sources, scorer_names_capitalised=squads_style == "more", squads=defaultdict(list))
    await sync_squads(session, ctx)
    for m in matches:
        await sync_match(session, ctx, m, path)
    return len(matches)


async def run_sync(
    *,
    competitions: list[CompetitionSeed] | None = None,
    teams: list[TeamSeed] | None = None,
    refresh_sources: bool = True,
) -> None:
    settings = get_settings()
    competitions = competitions if competitions is not None else load_competitions()
    teams = teams if teams is not None else load_teams()
    sources = settings.sources_dir
    if refresh_sources:
        ensure_sources(sources, competitions)

    maker = get_sessionmaker()
    async with maker() as session, session.begin():
        for comp_seed in competitions:
            await upsert_competition(session, comp_seed)
        await sync_teams(session, teams)
    if settings.wikidata_enabled:
        await verify_wikidata(competitions, teams)
    for comp_seed in competitions:
        # One transaction per competition-season: a bad file leaves no partial writes.
        async with maker() as session, session.begin():
            count = await sync_season(session, comp_seed, sources)
        log.info("%s %s: %d matches", comp_seed.name, comp_seed.season.label, count)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(run_sync())
    except SyncError as exc:
        log.error("sync failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

