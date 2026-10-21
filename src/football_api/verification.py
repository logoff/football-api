"""Verification of stored league results against an independent open reference.

For each season whose seed names a Wikipedia article, every cell of the article's results
grid is paired with the stored LEAGUE match of the same home and away teams (identified
through Wikidata QIDs only) and the match gets a status. The reference's values are only
compared and logged, never written (match-verification spec).

A season is verified again only when something it depends on changed: its data, a page it read,
or its turn in the weekly rotation (skip-unchanged-seasons D5). Otherwise its stored statuses are
reported as unchanged (D6).
"""

import logging
import math
import uuid
from collections import Counter
from collections.abc import Collection
from contextlib import AbstractContextManager
from datetime import UTC, date, datetime, timedelta
from functools import cache
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from football_api.domain.enums import CompetitionFormat, DecidedBy, EntityType, Stage, VerificationReference, VerificationStatus
from football_api.infra.db import get_sessionmaker
from football_api.infra.models import ExternalRef, Match, MatchVerification, Season, StandingVerification, Team
from football_api.ingestion.seeds import CompetitionSeed, SeasonSource, load_teams
from football_api.ingestion.wikipedia import MatchBox, ResultsGrid, StandingsLine, StandingsTable, WikipediaUnavailable
from football_api.season_check import SeasonKey, StoredCheck, record_verification, season_id, stored_checks
from football_api.season_tables import season_tables, wikidata_ids

log = logging.getLogger("football_api.verification")

WIKIDATA = "wikidata"
Score = tuple[int, int]
ROTATION_DAYS = 7  # every season is verified again at least about this often (D5)


class ResultsReference(Protocol):
    async def results_grid(self, title: str) -> ResultsGrid | None: ...

    async def match_boxes(self, title: str, *, qualifying: bool = False) -> list[MatchBox]: ...

    async def standings(self, title: str, *, qualifying: bool = False) -> list[StandingsTable]: ...

    async def qids(self, titles: list[str]) -> dict[str, str]: ...

    def record_pages(self) -> AbstractContextManager[dict[str, int]]:
        """Collect the title and revision ID of every page read inside the block."""
        ...

    async def revisions(self, titles: list[str]) -> dict[str, int]:
        """The current revision ID of each title that exists, following redirects."""
        ...


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


async def _stores_qualifying(seed: CompetitionSeed, src: SeasonSource) -> bool:
    """Whether the season holds qualifying matches, whose sub-articles are then worth reading."""
    async with get_sessionmaker()() as session:
        sid = await season_id(session, seed, src)
        if sid is None:
            return False
        stage = await session.scalar(
            select(Match.stage)
            .where(Match.season_id == sid, Match.stage.in_((Stage.QUALIFYING, Stage.PRELIMINARY, Stage.ROUND)))
            .limit(1)
        )
        return stage is not None


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
    used: set[int] = set()
    left: list[Match] = []
    for key, matches in stored.items():
        pairs = _pair(matches, by_pairing.get(key, []))
        for match, box in pairs:
            paired += 1
            used.add(id(box))
            await _record(session, label, names, match, box.score, box.shootout, now, counts)
        done = {match.id for match, _ in pairs}
        left += [m for m in matches if m.id not in done]
    # At neutral venues the sources may name the teams the other way round: a match left over pairs
    # with the one unused box of the reversed pairing on its date, compared with the box flipped.
    for match in left:
        day = match.kickoff_utc.date()
        reverse = [
            b
            for b in by_pairing.get((match.away_team_id, match.home_team_id), [])
            if id(b) not in used and b.day and abs(b.day - day) <= timedelta(days=1)
        ]
        if len(reverse) == 1:
            box = reverse[0]
            paired += 1
            used.add(id(box))
            await _record(session, label, names, match, _flip(box.score), _flip(box.shootout), now, counts)
    return counts, sum(len(m) for m in stored.values()) - paired


def _flip(score: tuple[int, int] | None) -> tuple[int, int] | None:
    return (score[1], score[0]) if score else None


@cache
def _seeded_qid_of_reference() -> dict[str, str]:
    """Wikidata items references use for a seeded team that has its own (the Dutch East Indies of
    1938, which Wikipedia links as Indonesia) → that team's item."""
    return {ref: t.wikidata for t in load_teams() if t.wikidata for ref in t.reference_wikidata}


def _as_seeded(title_qids: dict[str, str]) -> dict[str, str]:
    seeded = _seeded_qid_of_reference()
    return {title: seeded.get(qid, qid) for title, qid in title_qids.items()}


def _has_standings(seed: CompetitionSeed) -> bool:
    return seed.format in (CompetitionFormat.LEAGUE, CompetitionFormat.TOURNAMENT)


async def verify_seasons(
    targets: list[tuple[CompetitionSeed, SeasonSource]],
    reference: ResultsReference,
    *,
    now: datetime | None = None,
    changed: Collection[SeasonKey] | None = None,
) -> None:
    """Verify every target season that names a Wikipedia article: a results grid for leagues,
    match boxes for cups, then the final standings tables of leagues and tournaments.

    With `changed` (the seasons synced in this run), only the seasons due (D5) are verified; the
    others report their stored statuses. Without it, every season is verified. A season whose
    reference is unavailable, or has no grid or boxes, is skipped with a warning and keeps its
    statuses; nothing here raises for reference problems.
    """
    now = now or datetime.now(UTC)
    verifiable = [(seed, src) for seed, src in targets if src.wikipedia]
    async with get_sessionmaker()() as session:
        stored = await stored_checks(session)
    due = await _due(verifiable, stored, reference, changed, now)
    for seed, src in verifiable:
        label = f"{seed.name} {src.label}"
        last = stored.get((seed.wikidata, src.label))
        if (seed.wikidata, src.label) not in due and last is not None:
            await _report_unchanged(seed, label, last)
            continue
        with reference.record_pages() as pages:
            complete, unpaired = await _verify_matches(seed, src, label, reference, now)
            if _has_standings(seed):
                try:
                    complete = await verify_standings(seed, src, label, reference, now) and complete
                except SQLAlchemyError as exc:  # a data problem in one season mustn't stop the run
                    log.error("%s: standings verification failed: %s", label, exc)
                    complete = False
        if complete:  # an incomplete verification stores nothing, so the season is due next run
            async with get_sessionmaker()() as session, session.begin():
                if (sid := await season_id(session, seed, src)) is not None:
                    await record_verification(session, sid, dict(pages), unpaired, now)


async def _due(
    verifiable: list[tuple[CompetitionSeed, SeasonSource]],
    stored: dict[SeasonKey, StoredCheck],
    reference: ResultsReference,
    changed: Collection[SeasonKey] | None,
    now: datetime,
) -> set[SeasonKey]:
    """The seasons to verify again (D5): changed data, no complete verification of the current
    data, a page with a new revision, or a check older than the rotation period (at most a
    `ROTATION_DAYS`th of the seasons per run, oldest first)."""
    keys = [(seed.wikidata, src.label) for seed, src in verifiable]
    if changed is None:
        return set(keys)
    due: set[SeasonKey] = set()
    quiet: list[tuple[SeasonKey, StoredCheck]] = []
    for key in keys:
        last = stored.get(key)
        if (
            key in changed
            or last is None
            or last.verified_at is None
            or last.reference_revisions is None
            or last.reference_fingerprint != last.source_fingerprint
        ):
            due.add(key)
        else:
            quiet.append((key, last))
    resynced = len(due)
    titles = sorted({title for _, last in quiet for title in last.reference_revisions or {}})
    edited = 0
    if titles:
        try:
            current = await reference.revisions(titles)
        except WikipediaUnavailable as exc:
            log.warning("wikipedia revisions unavailable (%s); edited pages aren't detected this run", exc)
        else:
            for key, last in quiet:
                if any(current.get(title) != rev for title, rev in (last.reference_revisions or {}).items()):
                    due.add(key)
                    edited += 1
    stale = now - timedelta(days=ROTATION_DAYS)
    rest = sorted(
        (last.verified_at, key) for key, last in quiet if key not in due and last.verified_at and last.verified_at < stale
    )
    rotation = [key for _, key in rest[: math.ceil(len(keys) / ROTATION_DAYS)]]
    due.update(rotation)
    log.info(
        "verification: %d of %d seasons due (%d new or re-synced, %d with edited pages, %d in rotation)",
        len(due), len(keys), resynced, edited, len(rotation),
    )
    return due


async def _report_unchanged(seed: CompetitionSeed, label: str, last: StoredCheck) -> None:
    """Log a season's stored statuses in the same lines a verification logs (D6), with the date of
    the last check in place of the reference's values, which aren't stored."""
    since = f"wikipedia unchanged since {last.verified_at:%Y-%m-%d}" if last.verified_at else "wikipedia unchanged"
    async with get_sessionmaker()() as session:
        names = await _team_names(session)
        counts: Counter[VerificationStatus] = Counter()
        rows = await session.execute(
            select(Match, MatchVerification.status)
            .join(MatchVerification, MatchVerification.match_id == Match.id)
            .where(Match.season_id == last.season_id, MatchVerification.reference == VerificationReference.WIKIPEDIA)
            .order_by(Match.kickoff_utc)
        )
        for match, status in rows:
            counts[status] += 1
            if status in (VerificationStatus.MISMATCH, VerificationStatus.SOURCE_BEHIND):
                stored, stored_pens = _stored(match)
                log.warning(
                    "%s: %s %s v %s: stored %s, %s",
                    label, status.value, names[match.home_team_id], names[match.away_team_id], _fmt(stored, stored_pens), since,
                )
        log.info(
            "%s: verified against wikipedia: %s%s unchanged",
            label,
            " ".join(f"{s.value}={counts[s]}" for s in VerificationStatus),
            f" unpaired={last.unpaired}" if last.unpaired is not None else "",
        )
        if not _has_standings(seed):
            return
        table_rows = list(
            await session.execute(
                select(StandingVerification).where(
                    StandingVerification.season_id == last.season_id,
                    StandingVerification.reference == VerificationReference.WIKIPEDIA,
                )
            )
        )
        if not table_rows:
            return
        table_counts = Counter(v.status for (v,) in table_rows)
        mismatched = {(v.team_id, v.stage, v.phase, v.group_name) for (v,) in table_rows if v.status is VerificationStatus.MISMATCH}
        if mismatched:
            season = await session.get(Season, last.season_id)
            assert season is not None
            for table in await season_tables(session, season):
                for row in table.rows:
                    if (row.team, table.key.stage, table.key.phase, table.key.group or "") in mismatched:
                        ours = _line(row.position, row.played, row.won, row.drawn, row.lost, row.goals_for, row.goals_against, row.points)
                        log.warning("%s: MISMATCH table %s: stored %s, %s", label, names[row.team], ours, since)
    log.info(
        "%s: standings checked against wikipedia: %s unchanged",
        label,
        " ".join(f"{s.value}={table_counts[s]}" for s in (VerificationStatus.VERIFIED, VerificationStatus.MISMATCH, VerificationStatus.UNCONFIRMED)),
    )


async def _verify_matches(
    seed: CompetitionSeed, src: SeasonSource, label: str, reference: ResultsReference, now: datetime
) -> tuple[bool, int | None]:
    """Verify the season's matches: whether the comparison completed, and the number of stored
    matches no match box paired with (None for a results grid)."""
    assert src.wikipedia is not None
    cup = seed.format in (CompetitionFormat.CUP, CompetitionFormat.LEAGUE_CUP, CompetitionFormat.TOURNAMENT)
    try:
        if cup:
            boxes = await reference.match_boxes(src.wikipedia, qualifying=await _stores_qualifying(seed, src))
            if not boxes:
                log.warning("%s: no match boxes in %r; statuses unchanged", label, src.wikipedia)
                return False, None
            title_qids = _as_seeded(await reference.qids(sorted({t for b in boxes for t in (b.home, b.away)})))
            grid = None
        else:
            grid = await reference.results_grid(src.wikipedia)
            if grid is None:
                log.warning("%s: no results grid in %r; statuses unchanged", label, src.wikipedia)
                return False, None
            title_qids = _as_seeded(await reference.qids(grid.teams))
            boxes = []
    except WikipediaUnavailable as exc:
        log.warning("%s: reference unavailable (%s); statuses unchanged", label, exc)
        return False, None
    unpaired = None
    async with get_sessionmaker()() as session, session.begin():
        sid = await season_id(session, seed, src)
        if sid is None:
            log.warning("%s: season not in the database; nothing to verify", label)
            return False, None
        if grid is not None:
            counts = await apply_grid(session, label, sid, grid, title_qids, now)
        else:
            counts, unpaired = await apply_boxes(session, label, sid, boxes, title_qids, now)
    log.info(
        "%s: verified against wikipedia: %s%s",
        label,
        " ".join(f"{s.value}={counts[s]}" for s in VerificationStatus),
        f" unpaired={unpaired}" if unpaired is not None else "",
    )
    return True, unpaired


# --- standings (verify-standings design) ----------------------------------------------


def _line(position: int, played: int, won: int, drawn: int, lost: int, gf: int, ga: int, points: int) -> str:
    return f"pos {position}, P{played} W{won} D{drawn} L{lost} {gf}-{ga} {points} pts"


async def verify_standings(
    seed: CompetitionSeed, src: SeasonSource, label: str, reference: ResultsReference, now: datetime
) -> bool:
    """Compare the season's final tables with Wikipedia's and record a status per row (D3).

    Provisional tables keep no status. Nothing here raises for reference problems. Returns
    whether the comparison completed: false when the reference or the season is missing.
    """
    assert src.wikipedia is not None
    async with get_sessionmaker()() as session, session.begin():
        season = await session.get(Season, sid) if (sid := await season_id(session, seed, src)) else None
        if season is None:
            return False
        tables = await season_tables(session, season)
        finals = [t for t in tables if t.status == "final"]
        await session.execute(
            delete(StandingVerification).where(
                StandingVerification.season_id == season.id, StandingVerification.reference == VerificationReference.WIKIPEDIA
            )
        )
        if not finals:
            return True
        try:
            wiki = await reference.standings(src.wikipedia, qualifying=await _stores_qualifying(seed, src))
            title_qids = _as_seeded(await reference.qids(sorted({line.team for table in wiki for line in table})))
        except WikipediaUnavailable as exc:
            log.warning("%s: standings reference unavailable (%s); no standings statuses", label, exc)
            return False
        by_teams: dict[frozenset[str], dict[str, StandingsLine]] = {}
        for table in wiki:
            # Teams that withdrew are listed with no games (World Cup 1950): they aren't in our table.
            table = [line for line in table if line.played > 0]
            lines = {title_qids[line.team]: line for line in table if line.team in title_qids}
            if lines and len(lines) == len(table):
                by_teams.setdefault(frozenset(lines), lines)
        team_ids = [r.team for t in finals for r in t.rows]
        qid_of = await wikidata_ids(session, EntityType.TEAM, team_ids)
        names = await _team_names(session)
        counts: Counter[VerificationStatus] = Counter()
        for table in finals:
            qids = [qid_of.get(r.team) for r in table.rows]
            reference_lines = by_teams.get(frozenset(q for q in qids if q)) if all(qids) else None
            # Teams results can't separate may share a position, or be ordered by lots, in the
            # reference: a tied row agrees on any position within its tied block.
            block = {r.team: [o.position for o in table.rows if o.tied and o.points == r.points] for r in table.rows if r.tied}
            for row, qid in zip(table.rows, qids, strict=True):
                status = VerificationStatus.UNCONFIRMED
                if reference_lines is not None and qid is not None:
                    ref = reference_lines[qid]
                    position = ref.position if row.team in block and min(block[row.team]) <= ref.position <= max(block[row.team]) else row.position
                    ours = _line(position, row.played, row.won, row.drawn, row.lost, row.goals_for, row.goals_against, row.points)
                    theirs = _line(ref.position, ref.played, ref.won, ref.drawn, ref.lost, ref.goals_for, ref.goals_against, ref.points)
                    status = VerificationStatus.VERIFIED if ours == theirs else VerificationStatus.MISMATCH
                    if status is VerificationStatus.MISMATCH:
                        log.warning("%s: MISMATCH table %s: stored %s, wikipedia %s", label, names[row.team], ours, theirs)
                counts[status] += 1
                session.add(
                    StandingVerification(
                        season_id=season.id,
                        team_id=row.team,
                        stage=table.key.stage,
                        phase=table.key.phase,
                        group_name=table.key.group or "",
                        reference=VerificationReference.WIKIPEDIA,
                        status=status,
                        checked_at=now,
                    )
                )
    log.info(
        "%s: standings checked against wikipedia: %s",
        label,
        " ".join(f"{s.value}={counts[s]}" for s in (VerificationStatus.VERIFIED, VerificationStatus.MISMATCH, VerificationStatus.UNCONFIRMED)),
    )
    return True
