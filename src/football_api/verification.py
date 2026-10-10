"""Verification of stored league results against an independent open reference.

For each season whose seed names a Wikipedia article, every cell of the article's results
grid is paired with the stored LEAGUE match of the same home and away teams (identified
through Wikidata QIDs only) and the match gets a status. The reference's values are only
compared and logged, never written (match-verification spec).
"""

import logging
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from football_api.domain.enums import EntityType, Stage, VerificationReference, VerificationStatus
from football_api.infra.db import get_sessionmaker
from football_api.infra.models import ExternalRef, Match, MatchVerification, Season, Team
from football_api.ingestion.seeds import CompetitionSeed, SeasonSource
from football_api.ingestion.wikipedia import ResultsGrid, WikipediaUnavailable

log = logging.getLogger("football_api.verification")

WIKIDATA = "wikidata"
Score = tuple[int, int]


class ResultsReference(Protocol):
    async def results_grid(self, title: str) -> ResultsGrid | None: ...

    async def qids(self, titles: list[str]) -> dict[str, str]: ...


def classify(stored: Score | None, reference: Score | None) -> VerificationStatus | None:
    if stored is None and reference is None:
        return None
    if stored is None:
        return VerificationStatus.SOURCE_BEHIND
    if reference is None:
        return VerificationStatus.UNCONFIRMED
    return VerificationStatus.VERIFIED if stored == reference else VerificationStatus.MISMATCH


def _fmt(score: Score | None) -> str:
    return f"{score[0]}–{score[1]}" if score else "none"


async def _season_id(session: AsyncSession, seed: CompetitionSeed, src: SeasonSource) -> uuid.UUID | None:
    comp_id = (
        select(ExternalRef.entity_id)
        .where(
            ExternalRef.entity_type == EntityType.COMPETITION,
            ExternalRef.source == WIKIDATA,
            ExternalRef.source_id == seed.wikidata,
        )
        .scalar_subquery()
    )
    return await session.scalar(select(Season.id).where(Season.competition_id == comp_id, Season.label == src.label))


async def _teams_by_qid(session: AsyncSession, qids: set[str]) -> dict[str, uuid.UUID]:
    rows = await session.execute(
        select(ExternalRef.source_id, ExternalRef.entity_id).where(
            ExternalRef.entity_type == EntityType.TEAM,
            ExternalRef.source == WIKIDATA,
            ExternalRef.source_id.in_(qids),
        )
    )
    return {qid: team_id for qid, team_id in rows}


async def apply_grid(
    session: AsyncSession,
    label: str,
    season_id: uuid.UUID,
    grid: ResultsGrid,
    title_qids: dict[str, str],
    now: datetime,
) -> Counter[VerificationStatus]:
    """Compare one season with its grid and upsert the statuses. Returns the count per status."""
    team_of_qid = await _teams_by_qid(session, set(title_qids.values()))
    team_of_title: dict[str, uuid.UUID] = {}
    for title in grid.teams:
        team_id = team_of_qid.get(title_qids.get(title, ""))
        if team_id is None:
            log.warning("%s: reference team %r has no known Wikidata QID; its matches are not compared", label, title)
        else:
            team_of_title[title] = team_id
    reference: dict[tuple[uuid.UUID, uuid.UUID], Score | None] = {
        (team_of_title[c.home], team_of_title[c.away]): c.score
        for c in grid.cells
        if c.home in team_of_title and c.away in team_of_title
    }

    names = {team_id: name for team_id, name in await session.execute(select(Team.id, Team.name))}
    matches = await session.scalars(select(Match).where(Match.season_id == season_id, Match.stage == Stage.LEAGUE))
    counts: Counter[VerificationStatus] = Counter()
    for match in matches:
        key = (match.home_team_id, match.away_team_id)
        if key not in reference:
            continue
        stored = (match.home_score, match.away_score) if match.home_score is not None and match.away_score is not None else None
        ref = reference[key]
        status = classify(stored, ref)
        if status is None:
            await session.execute(
                delete(MatchVerification).where(
                    MatchVerification.match_id == match.id, MatchVerification.reference == VerificationReference.WIKIPEDIA
                )
            )
            continue
        counts[status] += 1
        if status in (VerificationStatus.MISMATCH, VerificationStatus.SOURCE_BEHIND):
            log.warning(
                "%s: %s %s v %s: stored %s, wikipedia %s",
                label, status.value, names[match.home_team_id], names[match.away_team_id], _fmt(stored), _fmt(ref),
            )
        stmt = insert(MatchVerification).values(
            match_id=match.id, reference=VerificationReference.WIKIPEDIA, status=status, checked_at=now
        )
        await session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_match_verification_match_id_reference",
                set_={"status": stmt.excluded.status, "checked_at": stmt.excluded.checked_at},
            )
        )
    return counts


async def verify_seasons(
    targets: list[tuple[CompetitionSeed, SeasonSource]], reference: ResultsReference, *, now: datetime | None = None
) -> None:
    """Verify every target season that names a Wikipedia article.

    A season whose reference is unavailable or has no grid is skipped with a warning and
    keeps its statuses; nothing here raises for reference problems.
    """
    now = now or datetime.now(UTC)
    for seed, src in targets:
        if not src.wikipedia:
            continue
        label = f"{seed.name} {src.label}"
        try:
            grid = await reference.results_grid(src.wikipedia)
            if grid is None:
                log.warning("%s: no results grid in %r; statuses unchanged", label, src.wikipedia)
                continue
            title_qids = await reference.qids(grid.teams)
        except WikipediaUnavailable as exc:
            log.warning("%s: reference unavailable (%s); statuses unchanged", label, exc)
            continue
        async with get_sessionmaker()() as session, session.begin():
            season_id = await _season_id(session, seed, src)
            if season_id is None:
                log.warning("%s: season not in the database; nothing to verify", label)
                continue
            counts = await apply_grid(session, label, season_id, grid, title_qids, now)
        log.info(
            "%s: verified against wikipedia: %s",
            label, " ".join(f"{s.value}={counts[s]}" for s in VerificationStatus),
        )
