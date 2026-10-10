"""Wikipedia results-grid reader (match-verification spec): parsing, polite access, title → QID."""

from pathlib import Path

import httpx
import pytest

from football_api.ingestion.wikipedia import (
    GridCell,
    WikipediaClient,
    WikipediaUnavailable,
    parse_results_grid,
)

FIXTURE = Path(__file__).parent / "fixtures" / "wikipedia" / "season.html"
REST = "https://wiki.test/api/rest_v1"
API = "https://wiki.test/w/api.php"


def test_grid_is_found_after_a_non_grid_table() -> None:
    grid = parse_results_grid(FIXTURE.read_text(encoding="utf-8"))
    assert grid is not None
    assert grid.teams == ["Alpha FC", "Beta CF", "Gamma United"]
    assert grid.cells == [
        GridCell("Alpha FC", "Beta CF", (2, 1)),  # score inside a rivalry link
        GridCell("Alpha FC", "Gamma United", (0, 0)),
        GridCell("Beta CF", "Alpha FC", (1, 3)),
        GridCell("Beta CF", "Gamma United", (3, 0)),  # footnote marker removed
        GridCell("Gamma United", "Alpha FC", None),  # linked placeholder `a`
        GridCell("Gamma United", "Beta CF", None),  # not played
    ]


def test_page_without_grid() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    standings_only = html[: html.index('<h2 id="Results">')] + "</body></html>"
    assert parse_results_grid(standings_only) is None


def test_grid_with_no_scores_yet_is_not_a_grid() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    for score in ("2–1", "0–0", "1–3", "3–0"):
        html = html.replace(score, "")
    assert parse_results_grid(html) is None


async def no_sleep(_: float) -> None:
    return None


def client_with(handler: httpx.MockTransport, sleeps: list[float] | None = None) -> WikipediaClient:
    async def record(delay: float) -> None:
        if sleeps is not None:
            sleeps.append(delay)

    return WikipediaClient(rest=REST, api=API, transport=handler, sleep=record)


async def test_results_grid_fetches_rendered_html_with_project_user_agent() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=FIXTURE.read_text(encoding="utf-8"))

    async with client_with(httpx.MockTransport(handler)) as wiki:
        grid = await wiki.results_grid("2025–26 La Liga")
    assert grid is not None and len(grid.cells) == 6
    assert seen[0].url.raw_path == b"/api/rest_v1/page/html/2025%E2%80%9326_La_Liga"
    ua = seen[0].headers["User-Agent"]
    assert ua.startswith("football-api/") and "github.com/logoff/football-api" in ua and "@" not in ua


async def test_one_retry_on_429_honouring_retry_after() -> None:
    responses = iter([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, text="<html></html>")])
    sleeps: list[float] = []
    async with client_with(httpx.MockTransport(lambda _: next(responses)), sleeps) as wiki:
        assert await wiki.results_grid("X") is None
    assert sleeps == [7.0]


async def test_retry_after_is_capped() -> None:
    responses = iter([httpx.Response(503, headers={"Retry-After": "3600"}), httpx.Response(200, text="")])
    sleeps: list[float] = []
    async with client_with(httpx.MockTransport(lambda _: next(responses)), sleeps) as wiki:
        await wiki.results_grid("X")
    assert sleeps == [30.0]


async def test_second_failure_is_unavailable() -> None:
    async with client_with(httpx.MockTransport(lambda _: httpx.Response(503))) as wiki:
        with pytest.raises(WikipediaUnavailable, match="HTTP 503"):
            await wiki.results_grid("X")


async def test_timeout_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with client_with(httpx.MockTransport(handler)) as wiki:
        with pytest.raises(WikipediaUnavailable):
            await wiki.results_grid("X")


async def test_missing_article_is_unavailable() -> None:
    async with client_with(httpx.MockTransport(lambda _: httpx.Response(404))) as wiki:
        with pytest.raises(WikipediaUnavailable, match="HTTP 404"):
            await wiki.results_grid("1900–01 La Liga")


async def test_qids_follow_normalisation_and_redirects_in_batches_of_50() -> None:
    batches: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        titles = request.url.params["titles"].split("|")
        batches.append(titles)
        assert request.url.params["redirects"] == "1" and request.url.params["ppprop"] == "wikibase_item"
        pages = [{"title": t, "pageprops": {"wikibase_item": f"Q{i}"}} for i, t in enumerate(titles) if t.startswith("Club")]
        query = {
            "normalized": [{"from": "club_alpha", "to": "Club alpha"}] if "club_alpha" in titles else [],
            "redirects": [{"from": "Club alpha", "to": "Club Alpha FC"}] if "club_alpha" in titles else [],
            "pages": pages + ([{"title": "Club Alpha FC", "pageprops": {"wikibase_item": "Q42"}}] if "club_alpha" in titles else []),
        }
        return httpx.Response(200, json={"query": query})

    titles = ["club_alpha", "No QID page", *(f"Club {i:03}" for i in range(60))]
    async with client_with(httpx.MockTransport(handler)) as wiki:
        qids = await wiki.qids(titles)
    assert [len(b) for b in batches] == [50, 12]
    assert qids["club_alpha"] == "Q42"
    assert "No QID page" not in qids
    assert len(qids) == 61


@pytest.mark.network
async def test_live_la_liga_2024_25_grid() -> None:
    async with WikipediaClient(rest="https://en.wikipedia.org/api/rest_v1", api="https://en.wikipedia.org/w/api.php") as wiki:
        grid = await wiki.results_grid("2024–25 La Liga")
        assert grid is not None and len(grid.teams) == 20
        assert sum(1 for c in grid.cells if c.score) == 380
        qids = await wiki.qids(grid.teams)
    assert qids["Real Madrid CF"] == "Q8682" or "Q8682" in qids.values()
    assert len(qids) == 20
