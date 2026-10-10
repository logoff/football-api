"""Competition-scoped, unattended sync runs (ingestion spec)."""

from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from football_api.infra.db import get_engine, get_sessionmaker
from football_api.infra.models import Competition, Match, Season
from football_api.ingestion.seeds import CompetitionSeed, TeamSeed
from football_api.sync import (
    RUN_LOCK_KEY,
    SchemaNotMigratedError,
    SyncInProgressError,
    UnknownCompetitionError,
    _main,  # pyright: ignore[reportPrivateUsage]
    parse_args,
    run_sync,
    select_competitions,
)

PREMIER_LEAGUE = "Q9448"
BUNDESLIGA = "Q82595"


async def table_counts() -> tuple[int, int, int]:
    async with get_sessionmaker()() as session:
        return (
            await session.scalar(select(func.count()).select_from(Competition)) or 0,
            await session.scalar(select(func.count()).select_from(Season)) or 0,
            await session.scalar(select(func.count()).select_from(Match)) or 0,
        )


def test_parse_args() -> None:
    args = parse_args(["--competition", "Q324867", "--competition", "Q9448", "--verify", "--no-refresh"])
    assert (args.competition, args.verify, args.no_refresh) == (["Q324867", "Q9448"], True, True)
    defaults = parse_args([])
    assert (defaults.competition, defaults.verify, defaults.no_refresh) == ([], False, False)


def test_select_competitions(fixture_competitions: list[CompetitionSeed]) -> None:
    assert select_competitions(fixture_competitions, []) == fixture_competitions
    assert [c.wikidata for c in select_competitions(fixture_competitions, [BUNDESLIGA, PREMIER_LEAGUE])] == [
        PREMIER_LEAGUE, BUNDESLIGA,
    ]
    with pytest.raises(UnknownCompetitionError, match="Q1"):
        select_competitions(fixture_competitions, [PREMIER_LEAGUE, "Q1"])


@pytest.mark.db
async def test_unknown_competition_exits_2_before_any_write(fresh_db: Path) -> None:
    assert await _main(parse_args(["--competition", "Q1", "--no-refresh"])) == 2
    assert await table_counts() == (0, 0, 0)


@pytest.mark.db
async def test_scoped_sync_touches_only_that_competition(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    report = await run_sync(
        competitions=select_competitions(fixture_competitions, [PREMIER_LEAGUE]), teams=fixture_teams, refresh_sources=False
    )
    assert [(c.wikidata, s.label) for c, s in report.synced] == [(PREMIER_LEAGUE, "2024-25")]
    async with get_sessionmaker()() as session:
        names = list(await session.scalars(select(Competition.name).join(Season)))
    assert names == ["Premier League"]


@pytest.mark.db
async def test_failing_season_does_not_block_the_others(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    (fresh_db / "deutschland/2024-25/1-bundesliga.txt").write_text("▪ Matchday 1\n  garbage line\n", encoding="utf-8")
    two = select_competitions(fixture_competitions, [PREMIER_LEAGUE, BUNDESLIGA])
    two = [c.model_copy(update={"seasons": [s.model_copy(update={"json_file": None}) for s in c.seasons]}) for c in two]

    report = await run_sync(competitions=two, teams=fixture_teams, refresh_sources=False)

    assert [c.name for c, _ in report.synced] == ["Premier League"]
    assert [c.name for c, _, _ in report.failed] == ["Bundesliga"]
    async with get_sessionmaker()() as session:
        seasons = list(await session.scalars(select(Competition.name).join(Season)))
    assert seasons == ["Premier League"]  # no partial Bundesliga season


@pytest.mark.db
async def test_schema_behind_the_code_refuses_to_sync(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(text("UPDATE alembic_version SET version_num = 'older'"))
    with pytest.raises(SchemaNotMigratedError, match="run migrations first"):
        await run_sync(competitions=fixture_competitions, teams=fixture_teams, refresh_sources=False)
    assert await table_counts() == (0, 0, 0)


@pytest.mark.db
async def test_concurrent_run_is_refused(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    async with get_engine().connect() as holder:
        assert await holder.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": RUN_LOCK_KEY})
        with pytest.raises(SyncInProgressError):
            await run_sync(competitions=fixture_competitions, teams=fixture_teams, refresh_sources=False)
        await holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": RUN_LOCK_KEY})
    assert await table_counts() == (0, 0, 0)
    report = await run_sync(competitions=fixture_competitions[:1], teams=fixture_teams, refresh_sources=False)
    assert not report.failed  # the lock was released
