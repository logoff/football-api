"""Verification against a reference grid (match-verification spec), with a fake reference."""

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, update

from football_api.domain.enums import VerificationStatus
from football_api.infra.db import get_engine, get_sessionmaker
from football_api.infra.models import Match, MatchVerification, Team
from football_api.ingestion.seeds import CompetitionSeed, TeamSeed
from football_api.ingestion.wikipedia import GridCell, ResultsGrid, WikipediaUnavailable
from football_api.sync import run_sync
from football_api.verification import classify, verify_seasons

pytestmark = pytest.mark.db

ARTICLE = "2024–25 Premier League"


def test_classify() -> None:
    assert classify((2, 1), (2, 1)) is VerificationStatus.VERIFIED
    assert classify((2, 1), (2, 2)) is VerificationStatus.MISMATCH
    assert classify((2, 1), None) is VerificationStatus.UNCONFIRMED
    assert classify(None, (1, 0)) is VerificationStatus.SOURCE_BEHIND
    assert classify(None, None) is None


class FakeReference:
    """Serves a grid built from the stored matches, with per-pairing overrides."""

    def __init__(self) -> None:
        self.grid: ResultsGrid | None = None
        self.qid_of: dict[str, str] = {}
        self.error: Exception | None = None
        self.requests: list[str] = []

    async def results_grid(self, title: str) -> ResultsGrid | None:
        self.requests.append(title)
        if self.error:
            raise self.error
        return self.grid

    async def qids(self, titles: list[str]) -> dict[str, str]:
        return {t: self.qid_of[t] for t in titles if t in self.qid_of}


async def stored_matches() -> list[tuple[str, str, tuple[int, int] | None]]:
    async with get_sessionmaker()() as session:
        home, away = Team.__table__.alias("home"), Team.__table__.alias("away")
        rows = await session.execute(
            select(home.c.name, away.c.name, Match.home_score, Match.away_score)
            .join(home, home.c.id == Match.home_team_id)
            .join(away, away.c.id == Match.away_team_id)
            .order_by(Match.kickoff_utc, home.c.name)
        )
        return [(h, a, (hs, as_) if hs is not None and as_ is not None else None) for h, a, hs, as_ in rows]


async def statuses() -> dict[tuple[str, str], tuple[VerificationStatus, datetime]]:
    async with get_sessionmaker()() as session:
        home, away = Team.__table__.alias("home"), Team.__table__.alias("away")
        rows = await session.execute(
            select(home.c.name, away.c.name, MatchVerification.status, MatchVerification.checked_at)
            .join(Match, Match.id == MatchVerification.match_id)
            .join(home, home.c.id == Match.home_team_id)
            .join(away, away.c.id == Match.away_team_id)
        )
        return {(h, a): (s, t) for h, a, s, t in rows}


@pytest.fixture
async def premier_league(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> tuple[list[CompetitionSeed], FakeReference, list[tuple[str, str, tuple[int, int] | None]]]:
    """A synced Premier League season that names a reference article, and a matching fake grid."""
    pl = next(c for c in fixture_competitions if c.name == "Premier League")
    pl = pl.model_copy(update={"seasons": [pl.seasons[0].model_copy(update={"wikipedia": ARTICLE})]})
    report = await run_sync(competitions=[pl], teams=fixture_teams, refresh_sources=False)
    assert not report.failed
    matches = await stored_matches()
    ref = FakeReference()
    ref.qid_of = {t.name: t.wikidata for t in fixture_teams if t.wikidata}
    teams = sorted({n for h, a, _ in matches for n in (h, a)})
    ref.grid = ResultsGrid(teams=teams, cells=[GridCell(h, a, s) for h, a, s in matches])
    return [pl], ref, matches


def with_cells(grid: ResultsGrid, overrides: dict[tuple[str, str], tuple[int, int] | None]) -> ResultsGrid:
    cells = [GridCell(c.home, c.away, overrides.get((c.home, c.away), c.score)) for c in grid.cells]
    return ResultsGrid(teams=grid.teams, cells=cells)


async def verify(competitions: list[CompetitionSeed], teams: list[TeamSeed], ref: FakeReference) -> None:
    report = await run_sync(competitions=competitions, teams=teams, refresh_sources=False, verify=True, reference=ref)
    assert not report.failed


async def test_each_status_and_the_report(
    premier_league: tuple[list[CompetitionSeed], FakeReference, list[tuple[str, str, tuple[int, int] | None]]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    competitions, ref, matches = premier_league
    (h1, a1, s1), (h2, a2, _), (h3, a3, _) = matches[0], matches[1], matches[2]
    assert s1 is not None
    ref.grid = with_cells(ref.grid or ResultsGrid([], []), {(h1, a1): (s1[0], s1[1] + 1), (h2, a2): None})
    async with get_engine().begin() as conn:  # the stored data lags behind for one match
        home_id = select(Team.id).where(Team.name == h3).scalar_subquery()
        away_id = select(Team.id).where(Team.name == a3).scalar_subquery()
        await conn.execute(
            update(Match).where(Match.home_team_id == home_id, Match.away_team_id == away_id).values(home_score=None, away_score=None)
        )

    with caplog.at_level(logging.INFO, logger="football_api.verification"):
        # A sync would restore the third match's score, so verify without re-syncing.
        await verify_seasons([(competitions[0], competitions[0].seasons[0])], ref)

    got = {k: s for k, (s, _) in (await statuses()).items()}
    assert got[(h1, a1)] is VerificationStatus.MISMATCH
    assert got[(h2, a2)] is VerificationStatus.UNCONFIRMED
    assert got[(h3, a3)] is VerificationStatus.SOURCE_BEHIND
    assert sum(s is VerificationStatus.VERIFIED for s in got.values()) == len(matches) - 3
    assert f"MISMATCH {h1} v {a1}: stored {s1[0]}–{s1[1]}, wikipedia {s1[0]}–{s1[1] + 1}" in caplog.text
    assert f"SOURCE_BEHIND {h3} v {a3}: stored none" in caplog.text
    assert f"Premier League 2024-25: verified against wikipedia: VERIFIED={len(matches) - 3} MISMATCH=1 UNCONFIRMED=1 SOURCE_BEHIND=1" in caplog.text


async def test_status_follows_the_sources_on_a_rerun(
    premier_league: tuple[list[CompetitionSeed], FakeReference, list[tuple[str, str, tuple[int, int] | None]]],
    fixture_teams: list[TeamSeed],
) -> None:
    competitions, ref, matches = premier_league
    h, a, _ = matches[0]
    full = ref.grid
    assert full is not None
    ref.grid = with_cells(full, {(h, a): None})
    await verify(competitions, fixture_teams, ref)
    first_status, first_checked = (await statuses())[(h, a)]
    assert first_status is VerificationStatus.UNCONFIRMED

    ref.grid = full
    await verify(competitions, fixture_teams, ref)
    status, checked = (await statuses())[(h, a)]
    assert status is VerificationStatus.VERIFIED and checked > first_checked


async def test_unknown_reference_team_is_skipped(
    premier_league: tuple[list[CompetitionSeed], FakeReference, list[tuple[str, str, tuple[int, int] | None]]],
    fixture_teams: list[TeamSeed],
    caplog: pytest.LogCaptureFixture,
) -> None:
    competitions, ref, matches = premier_league
    h = matches[0][0]
    del ref.qid_of[h]
    with caplog.at_level(logging.WARNING, logger="football_api.verification"):
        await verify(competitions, fixture_teams, ref)
    got = await statuses()
    assert all(h not in pair for pair in got)
    assert got and f"reference team '{h}' has no known Wikidata QID" in caplog.text


@pytest.mark.parametrize("problem", ["no grid", "unavailable"])
async def test_reference_problems_keep_existing_statuses(
    premier_league: tuple[list[CompetitionSeed], FakeReference, list[tuple[str, str, tuple[int, int] | None]]],
    fixture_teams: list[TeamSeed],
    problem: str,
) -> None:
    competitions, ref, _ = premier_league
    await verify(competitions, fixture_teams, ref)
    before = await statuses()
    assert before
    if problem == "no grid":
        ref.grid = None
    else:
        ref.error = WikipediaUnavailable("HTTP 503")
    await verify(competitions, fixture_teams, ref)  # never raises, run still succeeds
    assert await statuses() == before


async def test_only_seasons_with_a_reference_are_verified(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    bundesliga = [c for c in fixture_competitions if c.name == "Bundesliga"]
    ref = FakeReference()
    await verify(bundesliga, fixture_teams, ref)
    assert ref.requests == []
    assert await statuses() == {}


async def test_no_reference_values_are_stored(
    premier_league: tuple[list[CompetitionSeed], FakeReference, list[tuple[str, str, tuple[int, int] | None]]],
    fixture_teams: list[TeamSeed],
) -> None:
    competitions, ref, matches = premier_league
    h, a, s = matches[0]
    assert s is not None
    ref.grid = with_cells(ref.grid or ResultsGrid([], []), {(h, a): (9, 9)})
    await verify(competitions, fixture_teams, ref)
    async with get_engine().connect() as conn:
        columns = await conn.run_sync(lambda c: [col["name"] for col in inspect(c).get_columns("match_verification")])
    assert sorted(columns) == ["checked_at", "id", "match_id", "reference", "status"]
    assert (await stored_matches())[0] == (h, a, s)  # the stored score is untouched
    assert (await statuses())[(h, a)][0] is VerificationStatus.MISMATCH
    assert datetime.now(UTC) >= (await statuses())[(h, a)][1]
