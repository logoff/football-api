"""Matches whose source gives no date (la-liga-history-from-wikipedia D1–D3; matches and standings specs)."""

from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from sqlalchemy import func, select

from football_api import sync
from football_api.infra.db import get_sessionmaker
from football_api.infra.models import Match, Season
from football_api.ingestion.openfootball.text_parser import ParsedMatch
from football_api.ingestion.seeds import CompetitionSeed, TeamSeed
from football_api.sync import run_sync, select_competitions

PREMIER_LEAGUE = "Q9448"


def undating(monkeypatch: pytest.MonkeyPatch, keep_date: Callable[[ParsedMatch], bool]) -> None:
    """Read the fixture files as usual, then drop the date of every match `keep_date` rejects."""
    read = sync.read_matches

    def without_dates(*args: Any) -> tuple[list[ParsedMatch], str]:
        matches, path = read(*args)
        return [m if keep_date(m) else replace(m, day=None, kickoff=None, utc_offset=None) for m in matches], path

    monkeypatch.setattr(sync, "read_matches", without_dates)


async def sync_premier_league(competitions: list[CompetitionSeed], teams: list[TeamSeed], *, full: bool = False) -> None:
    report = await run_sync(
        competitions=select_competitions(competitions, [PREMIER_LEAGUE]), teams=teams, refresh_sources=False, full=full
    )
    assert not report.failed, report.failed


async def stored() -> tuple[Season, list[Match]]:
    async with get_sessionmaker()() as session:
        season = (await session.scalars(select(Season))).one()
        return season, list(await session.scalars(select(Match).order_by(Match.id)))


@pytest.mark.db
async def test_season_without_dates_syncs_with_null_kickoffs(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed], monkeypatch: pytest.MonkeyPatch
) -> None:
    undating(monkeypatch, lambda _: False)
    await sync_premier_league(fixture_competitions, fixture_teams)
    season, matches = await stored()
    assert matches and all(m.kickoff_utc is None and m.original_kickoff_utc is None for m in matches)
    assert season.starts_on is None and season.ends_on is None

    # A forced resync keeps every match, with its UUID and still no date.
    await sync_premier_league(fixture_competitions, fixture_teams, full=True)
    _, again = await stored()
    assert [(m.id, m.kickoff_utc) for m in again] == [(m.id, None) for m in matches]


@pytest.mark.db
async def test_mixed_season_spans_its_dated_matches(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed], monkeypatch: pytest.MonkeyPatch
) -> None:
    undating(monkeypatch, lambda m: m.line_no % 2 == 0)
    await sync_premier_league(fixture_competitions, fixture_teams)
    season, matches = await stored()
    dated = [m.kickoff_utc for m in matches if m.kickoff_utc is not None]
    assert dated and len(dated) < len(matches)
    assert season.starts_on is not None and season.ends_on is not None
    assert (season.starts_on, season.ends_on) <= (min(dated).date(), max(dated).date())
    assert all(m.original_kickoff_utc is None for m in matches)


@pytest.fixture
async def mixed_client(
    fresh_db: Path,
    fixture_competitions: list[CompetitionSeed],
    fixture_teams: list[TeamSeed],
    monkeypatch: pytest.MonkeyPatch,
    fixture_seeds: None,
) -> AsyncIterator[httpx.AsyncClient]:
    """The Premier League fixture season with every other match's date dropped, behind the API."""
    from football_api.api.app import create_app

    undating(monkeypatch, lambda m: m.line_no % 2 == 0)
    await sync_premier_league(fixture_competitions, fixture_teams)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c


async def get(client: httpx.AsyncClient, url: str, status: int = 200) -> dict[str, Any]:
    resp = await client.get(url)
    assert resp.status_code == status, resp.text
    return cast(dict[str, Any], resp.json())


@pytest.mark.db
async def test_undated_matches_list_last_across_pages(mixed_client: httpx.AsyncClient) -> None:
    season, matches = await stored()
    items: list[dict[str, Any]] = []
    url = f"/v1/matches?season_id={season.id}&limit=3"
    while url:
        body = await get(mixed_client, url)
        items += body["data"]
        cursor = body["next_cursor"]
        url = f"/v1/matches?season_id={season.id}&limit=3&cursor={cursor}" if cursor else ""
    assert sorted(i["id"] for i in items) == sorted(str(m.id) for m in matches)
    kickoffs = [i["kickoff_utc"] for i in items]
    undated = kickoffs.index(None)
    assert all(k is not None for k in kickoffs[:undated]) and all(k is None for k in kickoffs[undated:])
    assert kickoffs[:undated] == sorted(kickoffs[:undated])
    assert [i["id"] for i in items[undated:]] == sorted(i["id"] for i in items[undated:])


@pytest.mark.db
async def test_date_range_leaves_undated_matches_out(mixed_client: httpx.AsyncClient) -> None:
    season, matches = await stored()
    body = await get(mixed_client, f"/v1/matches?season_id={season.id}&from=1900-01-01&to=2100-12-31&limit=200")
    assert len(body["data"]) == sum(1 for m in matches if m.kickoff_utc is not None)


@pytest.mark.db
async def test_standings_count_undated_matches_but_refuse_a_past_date(mixed_client: httpx.AsyncClient) -> None:
    season, matches = await stored()
    async with get_sessionmaker()() as session:
        counted = await session.scalar(
            select(func.count()).select_from(Match).where(Match.season_id == season.id, Match.home_score.is_not(None))
        )
    body = await get(mixed_client, f"/v1/seasons/{season.id}/standings")
    [table] = body["tables"]
    assert sum(r["played"] for r in table["rows"]) == 2 * (counted or 0)

    error = await get(mixed_client, f"/v1/seasons/{season.id}/standings?as_of=2024-09-01", 422)
    assert error["error"]["code"] == "season_without_dates"

    resp = await mixed_client.post(
        "/graphql", json={"query": f'{{ season(id: "{season.id}") {{ standings(asOf: "2024-09-01") {{ seasonId }} }} }}'}
    )
    [gql_error] = resp.json()["errors"]
    assert gql_error["extensions"]["code"] == "season_without_dates"

    undated = next(m for m in matches if m.kickoff_utc is None)
    resp = await mixed_client.post("/graphql", json={"query": f'{{ match(id: "{undated.id}") {{ kickoffUtc }} }}'})
    assert resp.json()["data"]["match"]["kickoffUtc"] is None
