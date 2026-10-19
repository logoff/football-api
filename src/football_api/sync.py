"""`just sync`: reconcile seeds, Wikidata and openfootball into the database.

Order: schema and run-lock checks → competitions and teams from `seeds/` → Wikidata
check of seeded QIDs → one transaction per competition-season for the openfootball
data. Every write is an upsert on a natural key (ingestion spec, "Idempotency"), so an
unchanged re-run rewrites identical values and creates nothing.

    python -m football_api.sync [--competition QID ...] [--verify] [--no-refresh]

Exit codes: 0 every requested season synced (verification findings never fail a run),
1 a season or the seed step failed, 2 usage error (e.g. unknown QID), 3 database schema
not migrated to head, 4 another sync holds the run lock.
"""

import argparse
import asyncio
import logging
import sys
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import delete, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from football_api.domain.enums import Coverage, EntityType, MatchStatus, SeasonStatus, Side, Stage, TeamKind
from football_api.infra.db import get_engine, get_sessionmaker
from football_api.infra.models import (
    Card,
    Competition,
    ExternalRef,
    Goal,
    LineupEntry,
    Match,
    Player,
    PlayerTeamSeason,
    Season,
    Substitution,
    Team,
    TeamSeason,
    Venue,
)
from football_api.infra.settings import get_settings
from football_api.ingestion.openfootball.events import MatchEvents, SideEvents, parse_events_file
from football_api.ingestion.openfootball.json_reader import is_current, read_json
from football_api.ingestion.openfootball.names import fold, short_name_matches, split_capitalised
from football_api.ingestion.openfootball.squads import SquadPlayer, parse_more_squads, parse_per_team_squad
from football_api.ingestion.openfootball.text_parser import ParsedMatch, normalize_stage, parse_file
from football_api.ingestion.seeds import CompetitionSeed, SeasonSource, TeamSeed, load_competitions, load_teams
from football_api.ingestion.sources import ensure_sources
from football_api.ingestion.wikidata import WikidataUnavailable, verify_qids
from football_api.ingestion.wikipedia import WikipediaClient
from football_api.verification import ResultsReference, verify_seasons

log = logging.getLogger("football_api.sync")

OPENFOOTBALL = "openfootball"
WIKIDATA = "wikidata"


# Arbitrary, fixed key for pg_try_advisory_lock: one sync at a time per database.
RUN_LOCK_KEY = 0x666F6F74  # "foot"


class SyncError(Exception):
    pass


class UnknownCompetitionError(SyncError):
    def __init__(self, qids: list[str]) -> None:
        super().__init__(f"no competition in seeds/competitions.yaml has Wikidata QID {', '.join(qids)}")


class SchemaNotMigratedError(SyncError):
    pass


class SyncInProgressError(SyncError):
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
    comp.format = seed.format
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


async def release_moved_aliases(session: AsyncSession, seeds: list[TeamSeed]) -> None:
    """Drop the reference of an alias that now belongs to another entry: one listed under a seed
    while pointing at a team another seed claims through its Wikidata QID (an alias moved between
    clubs, e.g. `Liverpool (URU)` away from Liverpool F.C.). The entry it moved to then resolves
    to its own team."""
    owner_by_team: dict[uuid.UUID, int] = {}
    for i, seed in enumerate(seeds):
        if seed.wikidata and (team_id := await lookup_ref(session, EntityType.TEAM, WIKIDATA, seed.wikidata)):
            owner_by_team[team_id] = i
    for i, seed in enumerate(seeds):
        for alias in seed.openfootball:
            team_id = await lookup_ref(session, EntityType.TEAM, OPENFOOTBALL, alias)
            if team_id is not None and owner_by_team.get(team_id, i) != i:
                log.info("teams.yaml: alias %r moves from %s to %r", alias, team_id, seed.name)
                await session.execute(
                    delete(ExternalRef).where(
                        ExternalRef.entity_type == EntityType.TEAM,
                        ExternalRef.source == OPENFOOTBALL,
                        ExternalRef.source_id == alias,
                    )
                )


async def sync_teams(session: AsyncSession, seeds: list[TeamSeed]) -> None:
    await release_moved_aliases(session, seeds)
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
            # A corrected QID replaces the old one rather than sitting next to it.
            await session.execute(
                delete(ExternalRef).where(
                    ExternalRef.entity_type == EntityType.TEAM,
                    ExternalRef.entity_id == team.id,
                    ExternalRef.source == WIKIDATA,
                    ExternalRef.source_id != seed.wikidata,
                )
            )
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
    src: SeasonSource
    season: Season
    sources: Path
    scorer_names_capitalised: bool
    squads: dict[uuid.UUID, list[tuple[Player, str]]]  # team_id → [(player, display)]
    seen: set[uuid.UUID] = field(default_factory=lambda: set[uuid.UUID]())  # matches this sync matched or created


async def resolve_team(session: AsyncSession, path: str, line_no: int, name: str) -> uuid.UUID:
    team_id = await lookup_ref(session, EntityType.TEAM, OPENFOOTBALL, name)
    if team_id is None:
        raise UnknownTeamError(path, line_no, name)
    return team_id


def kickoff_utc(m: ParsedMatch, tz: str, path: str) -> datetime:
    """Line offset first, then the file's configured zone (design.md, "Kickoff time zones").

    A match with a date but no time keeps its date: midnight UTC on that day, whatever the zone.
    """
    if m.kickoff is None:
        return date_only_kickoff(m.day)
    local = datetime.combine(m.day, m.kickoff)
    if m.utc_offset is not None:
        return (local - m.utc_offset).replace(tzinfo=UTC)
    if tz == "inline":
        raise SyncError(f"{path}:{m.line_no}: no UTC offset on the line and the file's tz is `inline`")
    return local.replace(tzinfo=ZoneInfo(tz)).astimezone(UTC)


def date_only_kickoff(day: date) -> datetime:
    return datetime.combine(day, time(0, 0), tzinfo=UTC)


def is_date_only(kickoff: datetime, day: date, tz: str) -> bool:
    """Whether a stored kickoff is the date-only placeholder for `day`, including the local-midnight
    value earlier syncs wrote for files with a named zone."""
    if kickoff == date_only_kickoff(day):
        return True
    return tz != "inline" and kickoff == datetime.combine(day, time(0, 0), tzinfo=ZoneInfo(tz)).astimezone(UTC)


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
    squad_src = ctx.src.squads
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
            session, EntityType.PLAYER, player.id, OPENFOOTBALL, f"{ctx.src.file}#{sp.team}#{sp.name.display}"
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


def occurrences(matches: list[ParsedMatch], team_of: dict[str, uuid.UUID]) -> list[int]:
    """Number each listing within its (stage, home, away): a pairing listed again after a game with
    a score is a further game (a cup re-replay); listed again after one without, it is the same
    game rescheduled (matches spec, Match record)."""
    last: dict[tuple[Stage, uuid.UUID, uuid.UUID], tuple[int, bool]] = {}
    out: list[int] = []
    for m in matches:
        key = (normalize_stage(m.round_label)[0], team_of[m.home], team_of[m.away])
        previous, played = last.get(key, (0, True))
        occurrence = previous + 1 if played else previous
        last[key] = (occurrence, m.score is not None)
        out.append(occurrence)
    return out


async def sync_match(session: AsyncSession, ctx: SeasonContext, m: ParsedMatch, path: str, occurrence: int) -> Match:
    home_id = await resolve_team(session, path, m.line_no, m.home)
    away_id = await resolve_team(session, path, m.line_no, m.away)
    stage, matchday = normalize_stage(m.round_label)
    kickoff = kickoff_utc(m, ctx.src.tz, path)
    key = f"{path}#{stage.value}#{m.home}#{m.away}" + (f"#{occurrence}" if occurrence > 1 else "")
    match = await session.scalar(
        select(Match).where(
            Match.season_id == ctx.season.id,
            Match.stage == stage,
            Match.home_team_id == home_id,
            Match.away_team_id == away_id,
            Match.occurrence == occurrence,
        )
    )
    if match is None:
        # The source may have relabelled the round (`10. Runde` → `Round of 32`): reuse the match of
        # the same teams and date this sync hasn't matched yet, so it keeps its UUID.
        match = await session.scalar(
            select(Match)
            .where(
                Match.season_id == ctx.season.id,
                Match.home_team_id == home_id,
                Match.away_team_id == away_id,
                Match.id.not_in(ctx.seen),
                Match.kickoff_utc.between(kickoff - timedelta(days=1), kickoff + timedelta(days=1)),
            )
            .order_by(Match.kickoff_utc)
        )
        if match is not None:
            log.info("%s: %s v %s moved from %s to %s", path, m.home, m.away, match.stage.value, stage.value)
            match.stage, match.occurrence = stage, occurrence
            await session.execute(
                delete(ExternalRef).where(
                    ExternalRef.entity_type == EntityType.MATCH,
                    ExternalRef.entity_id == match.id,
                    ExternalRef.source == OPENFOOTBALL,
                )
            )
    if match is None:
        # The same listing, now resolving to another team (an alias moved to its own club in
        # teams.yaml): the match follows it and keeps its UUID.
        listed = await lookup_ref(session, EntityType.MATCH, OPENFOOTBALL, key)
        if listed is not None and listed not in ctx.seen:
            match = await session.get(Match, listed)
        if match is not None:
            log.info("%s: %s v %s now resolves to other teams", path, m.home, m.away)
            match.home_team_id, match.away_team_id = home_id, away_id
    if match is None:
        match = Match(
            season_id=ctx.season.id,
            stage=stage,
            home_team_id=home_id,
            away_team_id=away_id,
            occurrence=occurrence,
            kickoff_utc=kickoff,
        )
        session.add(match)
    else:
        # A time appearing for a date-only fixture on the same day is not a move.
        moved = match.kickoff_utc != kickoff and not is_date_only(match.kickoff_utc, m.day, ctx.src.tz)
        if moved and match.original_kickoff_utc is None:
            match.original_kickoff_utc = match.kickoff_utc
        elif match.original_kickoff_utc is not None and is_date_only(match.original_kickoff_utc, m.day, ctx.src.tz):
            match.original_kickoff_utc = None  # recorded by earlier syncs for such a time appearing
    match.kickoff_utc = kickoff
    match.matchday, match.round_label, match.status = matchday, m.round_label, m.status
    match.awarded = m.awarded
    match.venue_id = await upsert_venue(session, m.venue_name, m.venue_city)
    score = m.score
    match.home_score = score.home if score else None
    match.away_score = score.away if score else None
    match.decided_by = score.decided_by if score else None
    match.home_pens = score.home_pens if score else None
    match.away_pens = score.away_pens if score else None
    await session.flush()
    await ensure_ref(session, EntityType.MATCH, match.id, OPENFOOTBALL, key)
    ctx.seen.add(match.id)
    if m.goals_listed:
        await sync_goals(session, ctx, match, m)
    return match


# --- events (match-events) ------------------------------------------------------------

type MatchKey = tuple[date, uuid.UUID, uuid.UUID]  # (day as listed, home team, away team)


async def link_events(
    session: AsyncSession, path: str, events_file: list[tuple[ParsedMatch, MatchEvents]], synced: dict[MatchKey, list[Match]]
) -> dict[uuid.UUID, MatchEvents]:
    """Each events-file match → the one synced match of the same day and teams (design D2)."""
    linked: dict[uuid.UUID, MatchEvents] = {}
    for pm, events in events_file:
        home_id = await resolve_team(session, path, pm.line_no, pm.home)
        away_id = await resolve_team(session, path, pm.line_no, pm.away)
        candidates = synced.get((pm.day, home_id, away_id), [])
        if len(candidates) != 1:
            found = "no synced match" if not candidates else f"{len(candidates)} synced matches"
            raise SyncError(f"{path}:{pm.line_no}: {pm.home} v {pm.away} on {pm.day} links to {found}")
        linked[candidates[0].id] = events
    return linked


def event_name(raw: str) -> str:
    """Events files mark surnames in capitals, as squad files do: `Lionel MESSI` → `Lionel Messi`."""
    return split_capitalised(raw).display


async def sync_event_rows[R: (LineupEntry, Substitution, Card)](
    session: AsyncSession, model: type[R], match_ids: list[uuid.UUID], rows: dict[tuple[uuid.UUID, Side], list[dict[str, object]]]
) -> None:
    """Upsert `model` rows by (match, side, ordinal) in source order; delete ordinals the source no longer has."""
    current = {
        (r.match_id, r.side, r.ordinal): r for r in await session.scalars(select(model).where(model.match_id.in_(match_ids)))
    }
    for (match_id, side), values in rows.items():
        for ordinal, fields in enumerate(values, 1):
            row = current.pop((match_id, side, ordinal), None)
            if row is None:
                row = model(match_id=match_id, side=side, ordinal=ordinal)
                session.add(row)
            for name, value in fields.items():
                setattr(row, name, value)
    if current:
        await session.execute(delete(model).where(model.id.in_([r.id for r in current.values()])))


async def sync_events(session: AsyncSession, ctx: SeasonContext, synced: dict[MatchKey, list[Match]]) -> None:
    """Lineups, substitutions, cards, referee and attendance from the season's events file."""
    matches = [m for group in synced.values() for m in group]
    linked: dict[uuid.UUID, MatchEvents] = {}
    if ctx.src.events:
        events_file = parse_events_file(
            ctx.sources / ctx.src.events, start_year=ctx.src.start_year, display_path=ctx.src.events
        )
        linked = await link_events(session, ctx.src.events, events_file, synced)

    lineups: dict[tuple[uuid.UUID, Side], list[dict[str, object]]] = {}
    substitutions: dict[tuple[uuid.UUID, Side], list[dict[str, object]]] = {}
    cards: dict[tuple[uuid.UUID, Side], list[dict[str, object]]] = {}
    for match in matches:
        events = linked.get(match.id, MatchEvents())
        match.referee_name = event_name(events.referee) if events.referee else None
        match.attendance = events.attendance
        for side, team_id, side_events in (
            (Side.HOME, match.home_team_id, events.home),
            (Side.AWAY, match.away_team_id, events.away),
        ):
            squad = ctx.squads.get(team_id, [])

            def player(raw: str) -> uuid.UUID | None:
                found = resolve_scorer(raw, squad)
                return found.id if found else None

            se = side_events or SideEvents()
            key = (match.id, side)
            lineups[key] = [
                {
                    "player_id": player(e.name), "player_name": event_name(e.name), "role": e.role,
                    "line_index": e.line_index, "is_captain": e.is_captain,
                }
                for e in se.entries
            ]
            substitutions[key] = [
                {
                    "minute": s.minute, "added_minute": s.added_minute,
                    "player_off_id": player(s.player_off), "player_off_name": event_name(s.player_off),
                    "player_on_id": player(s.player_on), "player_on_name": event_name(s.player_on),
                }
                for s in se.substitutions
            ]
            cards[key] = [
                {
                    "minute": c.minute, "added_minute": c.added_minute,
                    "player_id": player(c.name), "player_name": event_name(c.name), "kind": c.kind,
                }
                for c in se.cards
            ]
    match_ids = [m.id for m in matches]
    await sync_event_rows(session, LineupEntry, match_ids, lineups)
    await sync_event_rows(session, Substitution, match_ids, substitutions)
    await sync_event_rows(session, Card, match_ids, cards)

    def coverage(rows: dict[tuple[uuid.UUID, Side], list[dict[str, object]]]) -> Coverage:
        return Coverage.FULL if any(rows.values()) else Coverage.NONE

    ctx.season.lineups_coverage = coverage(lineups)
    ctx.season.substitutions_coverage = coverage(substitutions)
    ctx.season.cards_coverage = coverage(cards)


def read_matches(seed: CompetitionSeed, s: SeasonSource, sources: Path) -> tuple[list[ParsedMatch], str]:
    text_matches = parse_file(sources / s.file, start_year=s.start_year, display_path=s.file)
    if s.json_file:
        if not (sources / s.json_file).exists():
            log.info("%s %s: JSON mirror %s missing; using text file", seed.name, s.label, s.json_file)
            return text_matches, s.file
        json_matches = read_json(sources / s.json_file)
        if is_current(json_matches, text_matches):
            return json_matches, s.json_file
        log.info("%s %s: JSON mirror not current; using text file", seed.name, s.label)
    return text_matches, s.file


async def sync_season(session: AsyncSession, seed: CompetitionSeed, src: SeasonSource, sources: Path) -> int:
    comp = await upsert_competition(session, seed)
    matches, path = read_matches(seed, src, sources)
    season = await session.scalar(select(Season).where(Season.competition_id == comp.id, Season.label == src.label))
    if season is None:
        season = Season(competition_id=comp.id, label=src.label)
        session.add(season)
    days: list[date] = [m.day for m in matches]
    season.starts_on, season.ends_on = min(days), max(days)
    season.status = (
        SeasonStatus.COMPLETED
        if all(m.status is not MatchStatus.SCHEDULED for m in matches)
        else SeasonStatus.IN_PROGRESS
    )
    season.scorers_coverage = Coverage.FULL if any(m.goals_listed for m in matches) else Coverage.NONE
    season.players_coverage = Coverage.FULL if src.squads else Coverage.NONE
    await session.flush()
    await ensure_ref(session, EntityType.SEASON, season.id, OPENFOOTBALL, src.file)

    team_of: dict[str, uuid.UUID] = {}
    for m in matches:
        team_of[m.home] = await resolve_team(session, path, m.line_no, m.home)
        team_of[m.away] = await resolve_team(session, path, m.line_no, m.away)
    for team_id in set(team_of.values()):
        if await session.get(TeamSeason, (team_id, season.id)) is None:
            session.add(TeamSeason(team_id=team_id, season_id=season.id))
    # A team no longer in the source (an alias moved to another club) leaves the season.
    await session.execute(
        delete(TeamSeason).where(TeamSeason.season_id == season.id, TeamSeason.team_id.not_in(set(team_of.values())))
    )

    squads_style = src.squads.style if src.squads else None
    ctx = SeasonContext(seed, src, season, sources, scorer_names_capitalised=squads_style == "more", squads=defaultdict(list))
    await sync_squads(session, ctx)
    synced: dict[MatchKey, list[Match]] = defaultdict(list)
    for m, occurrence in zip(matches, occurrences(matches, team_of), strict=True):
        match = await sync_match(session, ctx, m, path, occurrence)
        same_day = synced[(m.day, match.home_team_id, match.away_team_id)]
        if match not in same_day:  # a postponed game listed twice is one match
            same_day.append(match)
    await sync_events(session, ctx, synced)

    # Matches the source no longer lists go, with their references; goals and statuses cascade.
    stale = list(await session.scalars(select(Match.id).where(Match.season_id == season.id, Match.id.not_in(ctx.seen))))
    if stale:
        await session.execute(
            delete(ExternalRef).where(ExternalRef.entity_type == EntityType.MATCH, ExternalRef.entity_id.in_(stale))
        )
        await session.execute(delete(Match).where(Match.id.in_(stale)))
        log.info("%s %s: removed %d matches no longer in the source", seed.name, src.label, len(stale))
    return len(matches)


# --- run ---------------------------------------------------------------------------


@dataclass
class SyncReport:
    synced: list[tuple[CompetitionSeed, SeasonSource]] = field(
        default_factory=lambda: list[tuple[CompetitionSeed, SeasonSource]]()
    )
    failed: list[tuple[CompetitionSeed, SeasonSource, Exception]] = field(
        default_factory=lambda: list[tuple[CompetitionSeed, SeasonSource, Exception]]()
    )


def select_competitions(competitions: list[CompetitionSeed], qids: list[str]) -> list[CompetitionSeed]:
    """The seeds for `--competition` QIDs, in seed order; all of them when none is given."""
    if not qids:
        return competitions
    unknown = sorted(set(qids) - {c.wikidata for c in competitions})
    if unknown:
        raise UnknownCompetitionError(unknown)
    return [c for c in competitions if c.wikidata in qids]


async def check_schema() -> None:
    """Migrations belong to the API container; a sync never runs them (design D5)."""
    head = ScriptDirectory.from_config(Config(str(get_settings().alembic_ini))).get_current_head()
    async with get_engine().connect() as conn:
        try:
            current = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        except ProgrammingError:
            current = None
    if current != head:
        raise SchemaNotMigratedError(
            f"database schema is at {current or 'no revision'}, code expects {head}; run migrations first"
        )


@asynccontextmanager
async def run_lock() -> AsyncGenerator[None]:
    """Hold a session-level advisory lock for the whole run; a dead process releases it."""
    async with get_engine().connect() as conn:
        if not await conn.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": RUN_LOCK_KEY}):
            raise SyncInProgressError("another sync is in progress on this database")
        try:
            yield
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": RUN_LOCK_KEY})
            await conn.commit()


async def run_sync(
    *,
    competitions: list[CompetitionSeed] | None = None,
    teams: list[TeamSeed] | None = None,
    refresh_sources: bool = True,
    verify: bool = False,
    reference: ResultsReference | None = None,
) -> SyncReport:
    """Sync every season of `competitions`; a failing season is logged and reported, not raised.

    With `verify`, the seasons that synced and name a reference are then verified against it
    (`reference` defaults to English Wikipedia). Verification never fails the run.
    """
    settings = get_settings()
    competitions = competitions if competitions is not None else load_competitions()
    teams = teams if teams is not None else load_teams()
    sources = settings.sources_dir
    await check_schema()
    report = SyncReport()
    async with run_lock():
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
            for src in comp_seed.seasons:
                # One transaction per competition-season: a bad file leaves no partial writes.
                try:
                    async with maker() as session, session.begin():
                        count = await sync_season(session, comp_seed, src, sources)
                except Exception as exc:  # noqa: BLE001 — one bad season must not block the rest
                    log.error("%s %s: FAILED: %s", comp_seed.name, src.label, exc)
                    report.failed.append((comp_seed, src, exc))
                    continue
                log.info("%s %s: %d matches", comp_seed.name, src.label, count)
                report.synced.append((comp_seed, src))
        if verify and settings.wikipedia_enabled:
            if reference is not None:
                await verify_seasons(report.synced, reference)
            else:
                async with WikipediaClient(rest=settings.wikipedia_rest, api=settings.wikipedia_api) as wiki:
                    await verify_seasons(report.synced, wiki)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m football_api.sync", description="Reconcile sources into the database.")
    parser.add_argument(
        "--competition", action="append", default=[], metavar="QID",
        help="sync only this competition (Wikidata QID); repeatable. Default: all",
    )
    parser.add_argument("--verify", action="store_true", help="verify synced seasons that have a reference")
    parser.add_argument("--no-refresh", action="store_true", help="use the existing source checkouts as they are")
    return parser.parse_args(argv)


async def _main(args: argparse.Namespace) -> int:
    try:
        competitions = select_competitions(load_competitions(), args.competition)
    except UnknownCompetitionError as exc:
        log.error("%s", exc)
        return 2
    try:
        report = await run_sync(competitions=competitions, refresh_sources=not args.no_refresh, verify=args.verify)
    except SchemaNotMigratedError as exc:
        log.error("%s", exc)
        return 3
    except SyncInProgressError as exc:
        log.error("%s", exc)
        return 4
    except SyncError as exc:
        log.error("sync failed: %s", exc)
        return 1
    finally:
        await get_engine().dispose()
    if report.failed:
        log.error("%d season(s) failed: %s", len(report.failed), ", ".join(f"{c.name} {s.label}" for c, s, _ in report.failed))
        return 1
    return 0


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    sys.exit(asyncio.run(_main(parse_args(argv))))


if __name__ == "__main__":
    main()

