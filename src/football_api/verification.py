"""Verification of stored league results against an independent open reference.

For each season whose seed names a Wikipedia article, every cell of the article's results
grid is paired with the stored LEAGUE match of the same home and away teams (identified
through Wikidata QIDs only) and the match gets a status. The reference's values are only
compared and logged, never written (match-verification spec).
"""

import logging
import uuid
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from football_api.domain.enums import CompetitionFormat, DecidedBy, EntityType, Stage, VerificationReference, VerificationStatus
from football_api.infra.db import get_sessionmaker
from football_api.infra.models import ExternalRef, Match, MatchVerification, Season, Team
from football_api.ingestion.seeds import CompetitionSeed, SeasonSource
from football_api.ingestion.wikipedia import MatchBox, ResultsGrid, WikipediaUnavailable

log = logging.getLogger("football_api.verification")

WIKIDATA = "wikidata"
Score = tuple[int, int]


class ResultsReference(Protocol):
    async def results_grid(self, title: str) -> ResultsGrid | None: ...

    async def match_boxes(self, title: str) -> list[MatchBox]: ...

    async def qids(self, titles: list[str]) -> dict[str, str]: ...


def classify(stored: Score | None, reference: Score | None) -> VerificationStatus | None:
    if stored is None and reference is None:
        return None
    if stored is None:
        return VerificationStatus.SOURCE_BEHIND
    if reference is None:
        return VerificationStatus.UNCONFIRMED
    return VerificationStatus.VERIFIED if stored == reference else VerificationStatus.MISMATCH


def _fmt(score: Score | None, shootout: Score | None = None) -> str:
    if not score:
        return "none"
    return f"{score[0]}–{score[1]}" + (f" ({shootout[0]}–{shootout[1]} p)" if shootout else "")


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


async def _teams_of_titles(
    session: AsyncSession, label: str, titles: list[str], title_qids: dict[str, str]
) -> dict[str, uuid.UUID]:
    team_of_qid = await _teams_by_qid(session, set(title_qids.values()))
    team_of_title: dict[str, uuid.UUID] = {}
    for title in titles:
        team_id = team_of_qid.get(title_qids.get(title, ""))
        if team_id is None:
            log.warning("%s: reference team %r has no known Wikidata QID; its matches are not compared", label, title)
        else:
            team_of_title[title] = team_id
    return team_of_title


def _stored(match: Match) -> tuple[Score | None, Score | None]:
    score = (match.home_score, match.away_score) if match.home_score is not None and match.away_score is not None else None
    pens = (
        (match.home_pens, match.away_pens)
        if match.decided_by is DecidedBy.PENALTIES and match.home_pens is not None and match.away_pens is not None
        else None
    )
    return score, pens


async def _record(
    session: AsyncSession,
    label: str,
    names: dict[uuid.UUID, str],
    match: Match,
    ref: Score | None,
    ref_pens: Score | None,
    now: datetime,
    counts: Counter[VerificationStatus],
) -> None:
    """Compare one stored match with its reference result and upsert, or remove, its status."""
    stored, stored_pens = _stored(match)
    # An awarded match recorded with a level score names no winner, so it can't be compared.
    level_award = match.awarded and stored is not None and stored[0] == stored[1]
    status = None if level_award else classify(stored, ref)
    if status is VerificationStatus.VERIFIED and stored_pens and ref_pens and stored_pens != ref_pens:
        status = VerificationStatus.MISMATCH
    if status is None:
        await session.execute(
            delete(MatchVerification).where(
                MatchVerification.match_id == match.id, MatchVerification.reference == VerificationReference.WIKIPEDIA
            )
        )
        return
    counts[status] += 1
    if status in (VerificationStatus.MISMATCH, VerificationStatus.SOURCE_BEHIND):
        log.warning(
            "%s: %s %s v %s: stored %s, wikipedia %s",
            label, status.value, names[match.home_team_id], names[match.away_team_id],
            _fmt(stored, stored_pens), _fmt(ref, ref_pens),
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


async def _team_names(session: AsyncSession) -> dict[uuid.UUID, str]:
    return {team_id: name for team_id, name in await session.execute(select(Team.id, Team.name))}


async def apply_grid(
    session: AsyncSession,
    label: str,
    season_id: uuid.UUID,
    grid: ResultsGrid,
    title_qids: dict[str, str],
    now: datetime,
) -> Counter[VerificationStatus]:
    """Compare one league season with its grid and upsert the statuses. Returns the count per status."""
    team_of_title = await _teams_of_titles(session, label, grid.teams, title_qids)
    reference: dict[tuple[uuid.UUID, uuid.UUID], Score | None] = {
        (team_of_title[c.home], team_of_title[c.away]): c.score
        for c in grid.cells
        if c.home in team_of_title and c.away in team_of_title
    }
    names = await _team_names(session)
    matches = await session.scalars(select(Match).where(Match.season_id == season_id, Match.stage == Stage.LEAGUE))
    counts: Counter[VerificationStatus] = Counter()
    for match in matches:
        key = (match.home_team_id, match.away_team_id)
        if key in reference:
            await _record(session, label, names, match, reference[key], None, now, counts)
    return counts


def _pair(stored: list[Match], boxes: list[MatchBox]) -> list[tuple[Match, MatchBox]]:
    """Pair the stored matches and boxes of one (home, away) pairing (design D2): alone, they pair;
    otherwise by date (allowing a day for kickoffs stored after midnight UTC), then in date order."""
    if len(stored) == 1 and len(boxes) == 1:
        return [(stored[0], boxes[0])]
    pairs: list[tuple[Match, MatchBox]] = []
    left_matches, left_boxes = sorted(stored, key=lambda m: m.kickoff_utc), sorted(boxes, key=lambda b: b.day or date.max)
    for match in list(left_matches):
        day = match.kickoff_utc.date()
        box = next((b for b in left_boxes if b.day and abs(b.day - day) <= timedelta(days=1)), None)
        if box is not None:
            pairs.append((match, box))
            left_matches.remove(match)
            left_boxes.remove(box)
    pairs += list(zip(left_matches, left_boxes, strict=False))
    return pairs


async def apply_boxes(
    session: AsyncSession,
    label: str,
    season_id: uuid.UUID,
    boxes: list[MatchBox],
    title_qids: dict[str, str],
    now: datetime,
) -> tuple[Counter[VerificationStatus], int]:
    """Compare one cup season with its match boxes and upsert the statuses.

    Returns the count per status and the number of stored matches no box paired with.
    """
    team_of_title = await _teams_of_titles(session, label, sorted({t for b in boxes for t in (b.home, b.away)}), title_qids)
    by_pairing: dict[tuple[uuid.UUID, uuid.UUID], list[MatchBox]] = {}
    for box in boxes:
        if box.home in team_of_title and box.away in team_of_title:
            by_pairing.setdefault((team_of_title[box.home], team_of_title[box.away]), []).append(box)
    stored: dict[tuple[uuid.UUID, uuid.UUID], list[Match]] = {}
    for match in await session.scalars(select(Match).where(Match.season_id == season_id)):
        stored.setdefault((match.home_team_id, match.away_team_id), []).append(match)
    names = await _team_names(session)
    counts: Counter[VerificationStatus] = Counter()
    paired = 0
    for key, matches in stored.items():
        for match, box in _pair(matches, by_pairing.get(key, [])):
            paired += 1
            await _record(session, label, names, match, box.score, box.shootout, now, counts)
    return counts, sum(len(m) for m in stored.values()) - paired


async def verify_seasons(
    targets: list[tuple[CompetitionSeed, SeasonSource]], reference: ResultsReference, *, now: datetime | None = None
) -> None:
    """Verify every target season that names a Wikipedia article: a results grid for leagues,
    match boxes for cups.

    A season whose reference is unavailable, or has no grid or boxes, is skipped with a warning
    and keeps its statuses; nothing here raises for reference problems.
    """
    now = now or datetime.now(UTC)
    for seed, src in targets:
        if not src.wikipedia:
            continue
        label = f"{seed.name} {src.label}"
        cup = seed.format in (CompetitionFormat.CUP, CompetitionFormat.LEAGUE_CUP)
        try:
            if cup:
                boxes = await reference.match_boxes(src.wikipedia)
                if not boxes:
                    log.warning("%s: no match boxes in %r; statuses unchanged", label, src.wikipedia)
                    continue
                title_qids = await reference.qids(sorted({t for b in boxes for t in (b.home, b.away)}))
                grid = None
            else:
                grid = await reference.results_grid(src.wikipedia)
                if grid is None:
                    log.warning("%s: no results grid in %r; statuses unchanged", label, src.wikipedia)
                    continue
                title_qids = await reference.qids(grid.teams)
                boxes = []
        except WikipediaUnavailable as exc:
            log.warning("%s: reference unavailable (%s); statuses unchanged", label, exc)
            continue
        unpaired = None
        async with get_sessionmaker()() as session, session.begin():
            season_id = await _season_id(session, seed, src)
            if season_id is None:
                log.warning("%s: season not in the database; nothing to verify", label)
                continue
            if grid is not None:
                counts = await apply_grid(session, label, season_id, grid, title_qids, now)
            else:
                counts, unpaired = await apply_boxes(session, label, season_id, boxes, title_qids, now)
        log.info(
            "%s: verified against wikipedia: %s%s",
            label,
            " ".join(f"{s.value}={counts[s]}" for s in VerificationStatus),
            f" unpaired={unpaired}" if unpaired is not None else "",
        )
