"""What each season's last sync and verification saw, so unchanged seasons can be skipped
(skip-unchanged-seasons design).

A season's fingerprint hashes everything its sync reads (D1): the code (D2), its competition's
and its own seed entries, the team seeds, and every source file the season reads. The same
inputs always produce the same rows, so an equal fingerprint means re-syncing changes nothing.
"""

import hashlib
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

import football_api
from football_api.domain.enums import EntityType
from football_api.infra.models import ExternalRef, Match, Season, SeasonCheck
from football_api.ingestion.seeds import CompetitionSeed, SeasonSource, TeamSeed

WIKIDATA = "wikidata"
SeasonKey = tuple[str, str]  # (competition QID, season label)


def _digest(parts: Iterable[bytes]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(len(part).to_bytes(8, "big"))  # length-prefixed, so no two part lists hash alike
        h.update(part)
    return h.hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def tree_fingerprint(root: Path) -> str:
    """The `.py` files under `root`, with their relative paths, in sorted path order."""
    files = sorted(root.rglob("*.py"))
    return _digest(part for f in files for part in (str(f.relative_to(root)).encode(), f.read_bytes()))


@cache
def code_fingerprint() -> str:
    """The installed package's code (D2)."""
    return tree_fingerprint(Path(football_api.__file__).parent)


def teams_fingerprint(teams: list[TeamSeed]) -> str:
    return _digest([_canonical([t.model_dump(mode="json") for t in teams])])


def squad_paths(src: SeasonSource, sources: Path) -> list[list[Path]]:
    """The squad files each of the season's patterns matches, in sorted order."""
    return [sorted(sources.glob(pattern)) for pattern in src.squads.files] if src.squads else []


def season_inputs(src: SeasonSource, sources: Path) -> list[str]:
    """Every source file the season's sync reads, relative to `sources`."""
    files = [src.file, *(f for f in (src.json_file, src.events) if f)]
    return files + [str(p.relative_to(sources)) for paths in squad_paths(src, sources) for p in paths]


def season_fingerprint(seed: CompetitionSeed, src: SeasonSource, teams: str, sources: Path) -> str:
    """D1: code, seed entries, team seeds (`teams_fingerprint`) and source files."""
    parts = [
        code_fingerprint().encode(),
        _canonical(seed.model_dump(mode="json", exclude={"seasons"})),
        _canonical(src.model_dump(mode="json", by_alias=True)),
        teams.encode(),
    ]
    for name in season_inputs(src, sources):
        path = sources / name
        parts += [name.encode(), path.read_bytes() if path.is_file() else b"\0missing"]
    return _digest(parts)


async def season_id(session: AsyncSession, seed: CompetitionSeed, src: SeasonSource) -> uuid.UUID | None:
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


@dataclass(frozen=True)
class StoredCheck:
    season_id: uuid.UUID
    matches: int
    source_fingerprint: str | None
    reference_revisions: dict[str, int] | None
    reference_fingerprint: str | None
    verified_at: datetime | None


async def stored_checks(session: AsyncSession) -> dict[SeasonKey, StoredCheck]:
    """Every season's stored check and match count, by (competition QID, label)."""
    matches = select(Match.season_id, func.count().label("n")).group_by(Match.season_id).subquery()
    rows = await session.execute(
        select(ExternalRef.source_id, Season.label, Season.id, func.coalesce(matches.c.n, 0), SeasonCheck)
        .join(Season, Season.competition_id == ExternalRef.entity_id)
        .outerjoin(matches, matches.c.season_id == Season.id)
        .outerjoin(SeasonCheck, SeasonCheck.season_id == Season.id)
        .where(ExternalRef.entity_type == EntityType.COMPETITION, ExternalRef.source == WIKIDATA)
    )
    return {
        (qid, label): StoredCheck(
            sid,
            n,
            check.source_fingerprint if check else None,
            check.reference_revisions if check else None,
            check.reference_fingerprint if check else None,
            check.verified_at if check else None,
        )
        for qid, label, sid, n, check in rows
    }


async def record_sync(session: AsyncSession, season: uuid.UUID, fingerprint: str, now: datetime) -> None:
    stmt = insert(SeasonCheck).values(season_id=season, source_fingerprint=fingerprint, synced_at=now)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[SeasonCheck.season_id],
            set_={"source_fingerprint": stmt.excluded.source_fingerprint, "synced_at": stmt.excluded.synced_at},
        )
    )


async def record_verification(session: AsyncSession, season: uuid.UUID, revisions: dict[str, int], now: datetime) -> None:
    """Store the pages a complete verification read, against the data it checked."""
    stmt = insert(SeasonCheck).values(season_id=season, reference_revisions=revisions, verified_at=now)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[SeasonCheck.season_id],
            # The existing row's source fingerprint: the data this verification compared.
            set_={
                "reference_revisions": stmt.excluded.reference_revisions,
                "reference_fingerprint": SeasonCheck.source_fingerprint,
                "verified_at": stmt.excluded.verified_at,
            },
        )
    )
