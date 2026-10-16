"""A season's standings tables from the database (standings spec; verify-standings design D1).

The API and the standings verifier both build tables here, so they can't disagree about them.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date
from functools import cache
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from football_api.domain.enums import EntityType, MatchStatus, SeasonStatus, Stage
from football_api.infra.models import ExternalRef, Match, Season, Team
from football_api.ingestion.seeds import (
    CompetitionSeed,
    PointsAdjustment,
    StandingsSeeds,
    load_competitions,
    load_standings,
    load_teams,
)
from football_api.standings import Row, Rules, Settled, TableKey, TableMatch, rank, split_tables


@cache
def standings_seeds() -> tuple[dict[str, CompetitionSeed], StandingsSeeds]:
    """Ranking rules and curated adjustments, read once from the seeds the image ships."""
    competitions = load_competitions()
    return {c.wikidata: c for c in competitions}, load_standings(competitions=competitions, teams=load_teams())


async def wikidata_ids(session: AsyncSession, entity: EntityType, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
    rows = await session.execute(
        select(ExternalRef.entity_id, ExternalRef.source_id).where(
            ExternalRef.entity_type == entity, ExternalRef.source == "wikidata", ExternalRef.entity_id.in_(ids)
        )
    )
    return {entity_id: qid for entity_id, qid in rows}


@dataclass
class SeasonTable:
    key: TableKey
    status: Literal["final", "provisional"]
    rows: list[Row]
    adjustments: dict[uuid.UUID, list[PointsAdjustment]]


async def season_tables(session: AsyncSession, season: Season, as_of: date | None = None) -> list[SeasonTable]:
    """The season's tables, ranked with its competition's rules and curated adjustments.

    Empty when the competition declares no ranking rules for the season, or the season has no
    league or group matches.
    """
    seeds, curated = standings_seeds()
    comp_qid = (await wikidata_ids(session, EntityType.COMPETITION, [season.competition_id])).get(season.competition_id)
    comp_seed = seeds.get(comp_qid or "")
    src = next((s for s in comp_seed.seasons if s.label == season.label), None) if comp_seed else None
    era = comp_seed.era(src) if comp_seed and src else None
    if comp_seed is None or src is None or era is None:
        return []

    zone = UTC if src.tz == "inline" else ZoneInfo(src.tz)
    stored = (
        await session.scalars(
            select(Match).where(
                Match.season_id == season.id, Match.stage.in_([Stage.LEAGUE, Stage.GROUP]), Match.status != MatchStatus.CANCELLED
            )
        )
    ).all()

    def counted(m: Match) -> bool:
        return as_of is None or m.kickoff_utc.astimezone(zone).date() <= as_of

    team_ids = sorted({t for m in stored for t in (m.home_team_id, m.away_team_id)})
    names = {t.id: t.name for t in await session.scalars(select(Team).where(Team.id.in_(team_ids)))}
    id_of_qid = {qid: tid for tid, qid in (await wikidata_ids(session, EntityType.TEAM, team_ids)).items()}
    winners = {
        (id_of_qid[w.home], id_of_qid[w.away]): id_of_qid[w.home if w.winner == "home" else w.away]
        for w in curated.awards
        if w.competition == comp_qid and w.season == season.label and w.home in id_of_qid and w.away in id_of_qid
    }
    matches = [
        TableMatch(
            m.home_team_id,
            m.away_team_id,
            m.home_score if counted(m) else None,
            m.away_score if counted(m) else None,
            m.kickoff_utc,
            m.stage,
            m.round_label,
            winners.get((m.home_team_id, m.away_team_id)) if m.awarded and m.home_score == m.away_score else None,
        )
        for m in stored
    ]
    adjustments = [
        a
        for a in curated.adjustments
        if a.competition == comp_qid and a.season == season.label and (a.effective is None or as_of is None or a.effective <= as_of)
    ]
    settled = [
        Settled(tuple(id_of_qid[q] for q in o.order))
        for o in curated.orders
        if o.competition == comp_qid and o.season == season.label and all(q in id_of_qid for q in o.order)
    ]
    rules = Rules(era, points_per_game=src.ranking == "points_per_game")
    # Matches never played in a finished season (one stopped early) don't keep its tables open.
    over = season.status is SeasonStatus.COMPLETED and (as_of is None or (season.ends_on is not None and as_of >= season.ends_on))

    tables: list[SeasonTable] = []
    for table in split_tables(matches):
        members = table.teams
        applied: dict[uuid.UUID, list[PointsAdjustment]] = {}
        for a in adjustments:
            if a.team in id_of_qid and id_of_qid[a.team] in members:
                applied.setdefault(id_of_qid[a.team], []).append(a)
        ranked = rank(
            members,
            table.matches,
            rules,
            adjustments={t: sum(a.points for a in adj) for t, adj in applied.items()},
            settled=settled,
            name=lambda t: names.get(t, str(t)),
        )
        done = over or all(m.played for m in table.matches)
        tables.append(SeasonTable(table.key, "final" if done else "provisional", ranked, applied))
    return tables
