"""Verification against a reference grid (match-verification spec), with a fake reference."""

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select, update

from football_api.domain.enums import MatchStatus, SeasonStatus, VerificationStatus
from football_api.infra.db import get_engine, get_sessionmaker
from football_api.infra.models import Match, MatchVerification, Season, Team
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
    libertadores = [c for c in fixture_competitions if c.name == "CONMEBOL Copa Libertadores"]
    ref = FakeReference()
    await verify(libertadores, fixture_teams, ref)
    assert ref.requests == []
    assert await statuses() == {}


async def test_season_without_an_article_is_skipped_quietly(
    fresh_db: Path,
    fixture_competitions: list[CompetitionSeed],
    fixture_teams: list[TeamSeed],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A season seeded without `wikipedia` is not verified; its siblings are (match-verification spec)."""
    (fresh_db / "england/2023-24").mkdir()
    (fresh_db / "england/2023-24/1-premierleague.txt").write_text(
        (fresh_db / "england/2024-25/1-premierleague.txt").read_text(encoding="utf-8").replace("2024", "2023"),
        encoding="utf-8",
    )
    pl = next(c for c in fixture_competitions if c.name == "Premier League")
    current = pl.seasons[0].model_copy(update={"wikipedia": ARTICLE})
    earlier = current.model_copy(
        update={"label": "2023-24", "start_year": 2023, "file": "england/2023-24/1-premierleague.txt", "json_file": None, "wikipedia": None}
    )
    pl = pl.model_copy(update={"seasons": [earlier, current]})
    ref = FakeReference()
    ref.qid_of = {t.name: t.wikidata for t in fixture_teams if t.wikidata}
    with caplog.at_level(logging.WARNING, logger="football_api.verification"):
        report = await run_sync(competitions=[pl], teams=fixture_teams, refresh_sources=False)
        assert not report.failed
        matches = await stored_matches()  # both seasons have the same pairings and scores
        teams = sorted({n for h, a, _ in matches for n in (h, a)})
        ref.grid = ResultsGrid(teams=teams, cells=[GridCell(h, a, s) for h, a, s in matches])
        await verify_seasons([(pl, s) for s in pl.seasons], ref)

    assert ref.requests == [ARTICLE]
    assert caplog.text == ""
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            select(Season.label, func.count(MatchVerification.id))
            .join(Match, Match.season_id == Season.id)
            .outerjoin(MatchVerification, MatchVerification.match_id == Match.id)
            .group_by(Season.label)
            .order_by(Season.label)
        )
        assert [tuple(r) for r in rows] == [("2023-24", 0), ("2024-25", 20)]


async def test_cancelled_fixtures_get_no_status(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    """Fixtures the source marks cancelled have no score, close the season, and get no status (catalog spec)."""
    path = fresh_db / "england/2024-25/1-premierleague.txt"
    text = path.read_text(encoding="utf-8")
    for line in ("v AFC Bournemouth          1-1 (1-0)", "v Tottenham Hotspur FC     1-1 (0-1)"):
        assert line in text
        text = text.replace(line, line.split("  ")[0] + "  [cancelled]")
    path.write_text(text, encoding="utf-8")
    pl = next(c for c in fixture_competitions if c.name == "Premier League")
    pl = pl.model_copy(update={"seasons": [pl.seasons[0].model_copy(update={"json_file": None, "wikipedia": ARTICLE})]})
    report = await run_sync(competitions=[pl], teams=fixture_teams, refresh_sources=False)
    assert not report.failed
    matches = await stored_matches()
    ref = FakeReference()
    ref.qid_of = {t.name: t.wikidata for t in fixture_teams if t.wikidata}
    ref.grid = ResultsGrid(
        teams=sorted({n for h, a, _ in matches for n in (h, a)}), cells=[GridCell(h, a, s) for h, a, s in matches]
    )
    await verify(competitions=[pl], teams=fixture_teams, ref=ref)

    async with get_sessionmaker()() as session:
        cancelled = (await session.scalars(select(Match).where(Match.status == MatchStatus.CANCELLED))).all()
        season = await session.scalar(select(Season))
    assert len(cancelled) == 2
    assert all(m.home_score is None and m.away_score is None for m in cancelled)
    assert season is not None and season.status is SeasonStatus.COMPLETED
    got = await statuses()
    assert len(got) == len(matches) - 2
    assert all(s is VerificationStatus.VERIFIED for s, _ in got.values())


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
