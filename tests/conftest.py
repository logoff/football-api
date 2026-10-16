"""Database fixtures for `db`-marked tests.

Each fixture creates a throwaway database on the server in DATABASE_URL (default: the
compose stack from `just up`), migrates it with Alembic and points the app at it.
Without a reachable server, `db` tests are skipped.
"""

import os
import shutil
import subprocess
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from football_api.infra import db as infra_db
from football_api.infra.settings import get_settings
from football_api.ingestion.seeds import CompetitionSeed, TeamSeed, load_competitions, load_teams

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent
BASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://football:football@127.0.0.1:5432/football")


async def _admin(sql: str) -> None:
    engine = create_async_engine(BASE_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text(sql))
    finally:
        await engine.dispose()


async def create_database() -> str:
    name = f"football_test_{uuid.uuid4().hex[:8]}"
    try:
        await _admin(f'CREATE DATABASE "{name}"')
    except (OSError, OperationalError, DBAPIError) as exc:
        pytest.skip(f"PostgreSQL not reachable for db tests: {exc}")
    url = make_url(BASE_URL).set(database=name).render_as_string(hide_password=False)
    subprocess.run(["uv", "run", "alembic", "-x", f"url={url}", "upgrade", "head"], cwd=ROOT, check=True, capture_output=True)
    return url


async def drop_database(url: str) -> None:
    await infra_db.get_engine().dispose()
    await _admin(f'DROP DATABASE IF EXISTS "{make_url(url).database}" WITH (FORCE)')


def point_app_at(url: str, sources: Path) -> None:
    os.environ["DATABASE_URL"] = url
    os.environ["SOURCES_DIR"] = str(sources)
    os.environ["WIKIDATA_ENABLED"] = "false"
    get_settings.cache_clear()
    infra_db.get_engine.cache_clear()
    infra_db.get_sessionmaker.cache_clear()


@pytest.fixture(scope="session")
def fixture_competitions() -> list[CompetitionSeed]:
    return load_competitions(FIXTURES / "seeds" / "competitions.yaml")


@pytest.fixture(scope="session")
def fixture_teams() -> list[TeamSeed]:
    return load_teams(FIXTURES / "seeds" / "teams.yaml")


@pytest.fixture(scope="session")
async def synced_db(fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]) -> AsyncIterator[str]:
    """One database, synced once from the fixtures, shared by read-only tests."""
    from football_api.sync import run_sync

    url = await create_database()
    point_app_at(url, FIXTURES / "sources")
    await run_sync(competitions=fixture_competitions, teams=fixture_teams, refresh_sources=False)
    yield url
    await drop_database(url)


@pytest.fixture
def sources_copy(tmp_path: Path) -> Iterator[Path]:
    target = tmp_path / "sources"
    shutil.copytree(FIXTURES / "sources", target)
    yield target


@pytest.fixture
async def fresh_db(synced_db: str, sources_copy: Path) -> AsyncIterator[Path]:
    """An empty migrated database plus a writable copy of the sources, for tests that mutate data."""
    url = await create_database()
    point_app_at(url, sources_copy)
    yield sources_copy
    await drop_database(url)
    point_app_at(synced_db, FIXTURES / "sources")


@pytest.fixture
async def client(synced_db: str) -> AsyncIterator[httpx.AsyncClient]:
    from football_api.api.app import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def fixture_seeds(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Standings read the seeds the app ships; point them at the test subset."""
    from football_api import season_tables
    from football_api.infra.settings import get_settings

    monkeypatch.setenv("SEEDS_DIR", str(FIXTURES / "seeds"))
    get_settings.cache_clear()
    season_tables.standings_seeds.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()
    season_tables.standings_seeds.cache_clear()
