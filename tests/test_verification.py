"""Verification against a reference grid (match-verification spec), with a fake reference."""

import logging
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select, update

from football_api.domain.enums import MatchStatus, SeasonStatus, VerificationStatus
from football_api.infra.db import get_engine, get_sessionmaker
from football_api.infra.models import Match, MatchVerification, Season, Team
from football_api.ingestion.seeds import CompetitionSeed, TeamSeed
from football_api.ingestion.wikipedia import GridCell, MatchBox, ResultsGrid, WikipediaUnavailable
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
        self.boxes: list[MatchBox] = []
        self.qid_of: dict[str, str] = {}
        self.error: Exception | None = None
        self.requests: list[str] = []

    async def results_grid(self, title: str) -> ResultsGrid | None:
        self.requests.append(title)
        if self.error:
            raise self.error
        return self.grid

    async def match_boxes(self, title: str) -> list[MatchBox]:
        self.requests.append(title)
        if self.error:
            raise self.error
        return self.boxes

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
    (fresh_db / "england/2023-24").mkdir(exist_ok=True)
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


async def test_awarded_matches(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed], caplog: pytest.LogCaptureFixture
) -> None:
    """An awarded match with a level score isn't compared; one with the awarded score is (match-verification spec)."""
    pl = next(c for c in fixture_competitions if c.name == "Premier League")
    pl = pl.model_copy(update={"seasons": [pl.seasons[0].model_copy(update={"json_file": None, "wikipedia": ARTICLE})]})
    report = await run_sync(competitions=[pl], teams=fixture_teams, refresh_sources=False)
    assert not report.failed
    matches = await stored_matches()
    ref = FakeReference()
    ref.qid_of = {t.name: t.wikidata for t in fixture_teams if t.wikidata}
    level, decisive = ("Nottingham Forest", "AFC Bournemouth"), ("Manchester United", "Fulham")
    cells = [GridCell(h, a, (0, 3) if (h, a) == level else s) for h, a, s in matches]
    ref.grid = ResultsGrid(teams=sorted({n for h, a, _ in matches for n in (h, a)}), cells=cells)
    await verify([pl], fixture_teams, ref)
    assert (await statuses())[level][0] is VerificationStatus.MISMATCH  # 1–1 against 0–3, not yet awarded

    path = fresh_db / "england/2024-25/1-premierleague.txt"
    text = path.read_text(encoding="utf-8")
    for line in ("v AFC Bournemouth          1-1 (1-0)", "v Fulham FC                1-0 (0-0)"):
        assert line in text
        text = text.replace(line, line + "    [awarded]")
    path.write_text(text, encoding="utf-8")
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="football_api.verification"):
        await verify([pl], fixture_teams, ref)
    got = await statuses()
    assert level not in got
    assert got[decisive][0] is VerificationStatus.VERIFIED
    assert "AFC Bournemouth: stored" not in caplog.text


FA_CUP_ARTICLE = "2023–24 FA Cup"


async def fa_cup_synced(fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]) -> CompetitionSeed:
    fa = next(c for c in fixture_competitions if c.name == "FA Cup")
    fa = fa.model_copy(update={"seasons": [fa.seasons[0].model_copy(update={"wikipedia": FA_CUP_ARTICLE})]})
    report = await run_sync(competitions=[fa], teams=fixture_teams, refresh_sources=False)
    assert not report.failed
    return fa


def cup_reference(fixture_teams: list[TeamSeed], boxes: list[MatchBox]) -> FakeReference:
    ref = FakeReference()
    ref.qid_of = {t.name: t.wikidata for t in fixture_teams if t.wikidata}
    ref.boxes = boxes
    return ref


SCARBOROUGH, FOREST_GREEN = "Scarborough Athletic", "Forest Green Rovers"
COVENTRY, UNITED, CITY = "Coventry City", "Manchester United", "Manchester City"


def fa_cup_boxes(**overrides: MatchBox) -> list[MatchBox]:
    boxes = {
        "r1": MatchBox(date(2023, 11, 4), SCARBOROUGH, FOREST_GREEN, (1, 1)),
        "void": MatchBox(date(2023, 11, 14), FOREST_GREEN, SCARBOROUGH, None),  # the voided replay
        "r1b": MatchBox(date(2023, 12, 12), SCARBOROUGH, FOREST_GREEN, (2, 4)),
        "sf": MatchBox(date(2024, 4, 21), COVENTRY, UNITED, (3, 3), (2, 4)),
        "final": MatchBox(date(2024, 5, 25), CITY, UNITED, (1, 2)),
    }
    boxes.update(overrides)
    return list(boxes.values())


async def test_cup_season_verified_from_match_boxes(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed], caplog: pytest.LogCaptureFixture
) -> None:
    """Cups pair boxes by QIDs and date and compare shootouts (match-verification spec)."""
    fa = await fa_cup_synced(fixture_competitions, fixture_teams)
    ref = cup_reference(fixture_teams, fa_cup_boxes())
    with caplog.at_level(logging.INFO, logger="football_api.verification"):
        await verify_seasons([(fa, fa.seasons[0])], ref)
    got = await cup_statuses()
    assert got == {
        (SCARBOROUGH, FOREST_GREEN, date(2023, 11, 4)): VerificationStatus.VERIFIED,
        (SCARBOROUGH, FOREST_GREEN, date(2023, 12, 12)): VerificationStatus.VERIFIED,
        (COVENTRY, UNITED, date(2024, 4, 21)): VerificationStatus.VERIFIED,
        (CITY, UNITED, date(2024, 5, 25)): VerificationStatus.VERIFIED,
    }
    assert ref.requests == [FA_CUP_ARTICLE]
    assert "FA Cup 2023-24: verified against wikipedia: VERIFIED=4 MISMATCH=0 UNCONFIRMED=0 SOURCE_BEHIND=0 unpaired=0" in caplog.text


async def test_cup_shootout_and_no_result_boxes(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed], caplog: pytest.LogCaptureFixture
) -> None:
    fa = await fa_cup_synced(fixture_competitions, fixture_teams)
    boxes = fa_cup_boxes(
        sf=MatchBox(date(2024, 4, 21), COVENTRY, UNITED, (3, 3), (4, 2)),  # shootout differs
        final=MatchBox(date(2024, 5, 25), CITY, UNITED, None),  # e.g. `v` or `Void`
    )
    with caplog.at_level(logging.WARNING, logger="football_api.verification"):
        await verify_seasons([(fa, fa.seasons[0])], cup_reference(fixture_teams, boxes))
    got = await cup_statuses()
    assert got[(COVENTRY, UNITED, date(2024, 4, 21))] is VerificationStatus.MISMATCH
    assert got[(CITY, UNITED, date(2024, 5, 25))] is VerificationStatus.UNCONFIRMED
    assert "stored 3–3 (2–4 p), wikipedia 3–3 (4–2 p)" in caplog.text


async def test_cup_unpaired_match_is_counted(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed], caplog: pytest.LogCaptureFixture
) -> None:
    fa = await fa_cup_synced(fixture_competitions, fixture_teams)
    boxes = [b for b in fa_cup_boxes() if b.home != CITY]
    with caplog.at_level(logging.INFO, logger="football_api.verification"):
        await verify_seasons([(fa, fa.seasons[0])], cup_reference(fixture_teams, boxes))
    assert (CITY, UNITED, date(2024, 5, 25)) not in await cup_statuses()
    assert "unpaired=1" in caplog.text


async def cup_statuses() -> dict[tuple[str, str, date], VerificationStatus]:
    async with get_sessionmaker()() as session:
        home, away = Team.__table__.alias("home"), Team.__table__.alias("away")
        rows = await session.execute(
            select(home.c.name, away.c.name, Match.kickoff_utc, MatchVerification.status)
            .join(Match, Match.id == MatchVerification.match_id)
            .join(home, home.c.id == Match.home_team_id)
            .join(away, away.c.id == Match.away_team_id)
        )
        return {(h, a, k.date()): s for h, a, k, s in rows}
