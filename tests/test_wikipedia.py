"""Wikipedia results-grid reader (match-verification spec): parsing, polite access, title → QID."""

from datetime import date
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest

from football_api.ingestion.wikipedia import (
    PAGE_CACHE_SIZE,
    GridCell,
    WikipediaClient,
    WikipediaUnavailable,
    StandingsLine,
    merge_standings,
    parse_match_boxes,
    parse_standings,
    parse_subarticle_titles,
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


async def test_pages_record_their_revision_cached_or_not() -> None:
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetched.append(request.url.path)
        revision = "111" if request.url.path.endswith("/A") else "222"
        return httpx.Response(200, text="<html></html>", headers={"content-revision-id": revision})

    async with client_with(httpx.MockTransport(handler)) as wiki:
        await wiki.results_grid("A")
        with wiki.record_pages() as first:
            await wiki.results_grid("A")  # cached: no request, still recorded
            await wiki.results_grid("B")
        await wiki.results_grid("C")  # outside any block: not recorded
    assert first == {"A": 111, "B": 222}
    assert len(fetched) == 3


async def test_revisions_follow_redirects_and_skip_missing_pages_in_batches() -> None:
    batches: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        titles = request.url.params["titles"].split("|")
        batches.append(titles)
        assert request.url.params["prop"] == "info" and request.url.params["redirects"] == "1"
        pages: list[dict[str, object]] = [{"title": t, "lastrevid": 1000 + i} for i, t in enumerate(titles) if t.startswith("Season")]
        query: dict[str, object] = {"pages": pages}
        if "Old title" in titles:
            query["redirects"] = [{"from": "Old title", "to": "New title"}]
            pages.append({"title": "New title", "lastrevid": 42})
        if "Gone" in titles:
            pages.append({"title": "Gone", "missing": True})
        return httpx.Response(200, json={"query": query})

    titles = ["Old title", "Gone", *(f"Season {i:03}" for i in range(60))]
    async with client_with(httpx.MockTransport(handler)) as wiki:
        revisions = await wiki.revisions(titles)
    assert [len(b) for b in batches] == [50, 12]
    assert revisions["Old title"] == 42
    assert "Gone" not in revisions
    assert len(revisions) == 61


@pytest.mark.network
async def test_live_la_liga_2024_25_grid() -> None:
    async with WikipediaClient(rest="https://en.wikipedia.org/api/rest_v1", api="https://en.wikipedia.org/w/api.php") as wiki:
        grid = await wiki.results_grid("2024–25 La Liga")
        assert grid is not None and len(grid.teams) == 20
        assert sum(1 for c in grid.cells if c.score) == 380
        qids = await wiki.qids(grid.teams)
    assert qids["Real Madrid CF"] == "Q8682" or "Q8682" in qids.values()
    assert len(qids) == 20


@pytest.mark.network
async def test_live_dfb_pokal_2024_25_boxes() -> None:
    async with WikipediaClient(rest="https://en.wikipedia.org/api/rest_v1", api="https://en.wikipedia.org/w/api.php") as wiki:
        boxes = await wiki.match_boxes("2024–25 DFB-Pokal")
    assert len(boxes) == 63 and all(b.score for b in boxes)
    assert all(b.day for b in boxes)


CUP = Path(__file__).parent / "fixtures" / "wikipedia" / "cup.html"


def test_match_boxes_every_score_form() -> None:
    boxes = parse_match_boxes(CUP.read_text(encoding="utf-8"))
    got = [(b.home, b.away, b.score, b.shootout, b.awarded) for b in boxes]
    assert got == [
        ("Alpha Town F.C.", "Beta United F.C.", (2, 1), None, False),
        ("Gamma Rovers F.C.", "Delta City F.C.", (1, 1), None, False),  # a.e.t., footnote removed
        ("Epsilon F.C.", "Zeta Athletic F.C.", (2, 2), (4, 3), False),
        ("Alpha Town F.C.", "Gamma Rovers F.C.", (0, 1), None, False),  # aggregate ignored
        ("Eta F.C.", "Theta F.C.", (3, 0), None, True),
        ("Iota F.C.", "Kappa F.C.", (0, 3), None, True),
        ("Lambda F.C.", "Mu F.C.", None, None, False),  # w/o (0–3): no result
        ("Nu F.C.", "Xi F.C.", None, None, False),
        ("Omicron F.C.", "Pi F.C.", None, None, False),
        ("Rho F.C.", "Sigma F.C.", None, None, False),
        ("Tau F.C.", "Upsilon F.C.", None, None, False),
        # the box with an unlinked club is dropped: it can't be identified
        ("Alpha Town F.C.", "Gamma Rovers F.C.", (0, 0), (3, 4), False),  # Football box with a shootout row
    ]


def test_match_box_dates() -> None:
    boxes = parse_match_boxes(CUP.read_text(encoding="utf-8"))
    assert boxes[0].day == date(2030, 11, 5)  # hidden ISO date
    assert boxes[3].day == date(2030, 11, 8)  # plain-text date only
    assert boxes[-1].day == date(2031, 5, 20)  # Football box


def test_page_without_match_boxes() -> None:
    assert parse_match_boxes(FIXTURE.read_text(encoding="utf-8")) == []


def _box(day: str, home: str, away: str, score: str) -> str:
    return (
        '<table class="tmpl-football-box-collapsible"><tbody><tr>'
        f'<td><span class="dtstart">{day}</span></td>'
        f'<td class="vcard"><a href="./{home.replace(" ", "_")}" title="{home}">{home}</a></td>'
        f"<td><b>{score}</b></td>"
        f'<td class="vcard"><a href="./{away.replace(" ", "_")}" title="{away}">{away}</a></td><td></td>'
        "</tr></tbody></table>"
    )


SEASON = "Made-up Cup 2031"
PAGES = {
    SEASON: f"<html><head><title>{SEASON}</title></head><body>"
    + "".join(
        f'<a href="./{(SEASON + " " + sub).replace(" ", "_")}">{sub}</a>'
        for sub in ("Group A", "knockout phase", "qualification", "squads", "Femenina", "Group A", "Final", "qualifying stages")
    )
    + '<a href="./Other_article">other</a>'
    + _box("2031-07-01", "Alpha F.C.", "Beta F.C.", "1–0")
    + "</body></html>",
    f"{SEASON} Group A": _box("2031-07-01", "Alpha F.C.", "Beta F.C.", "1–0") + _box("2031-07-02", "Gamma F.C.", "Delta F.C.", "2–2"),
    f"{SEASON} knockout phase": _box("2031-07-10", "Alpha F.C.", "Gamma F.C.", "3–1"),
    f"{SEASON} qualification": _box("2030-03-01", "Qualifier F.C.", "Beta F.C.", "9–9"),
    f"{SEASON} qualifying stages": _box("2031-03-01", "Epsilon F.C.", "Beta F.C.", "0–1"),
}


def test_subarticles_follow_the_season_title_and_skip_noise() -> None:
    assert parse_subarticle_titles(PAGES[SEASON], SEASON) == [f"{SEASON} Group A", f"{SEASON} knockout phase", f"{SEASON} Final"]


def test_qualifying_subarticles_only_when_asked() -> None:
    """A competition's own qualifying stages, never a separate qualification tournament."""
    assert parse_subarticle_titles(PAGES[SEASON], SEASON, qualifying=True) == [
        f"{SEASON} Group A",
        f"{SEASON} knockout phase",
        f"{SEASON} Final",
        f"{SEASON} qualifying stages",
    ]


async def test_match_boxes_read_subarticles_once_each() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        title = unquote(request.url.raw_path.decode().rsplit("/", 1)[1]).replace("_", " ")
        requested.append(title)
        page = PAGES.get(title)
        return httpx.Response(200, text=page) if page is not None else httpx.Response(404)

    async with client_with(httpx.MockTransport(handler)) as wiki:
        boxes = await wiki.match_boxes(SEASON, qualifying=True)
    assert requested == [SEASON, f"{SEASON} Group A", f"{SEASON} knockout phase", f"{SEASON} Final", f"{SEASON} qualifying stages"]
    assert [(b.home, b.away, b.score) for b in boxes] == [
        ("Alpha F.C.", "Beta F.C.", (1, 0)),  # in the season article and in Group A: once
        ("Gamma F.C.", "Delta F.C.", (2, 2)),
        ("Alpha F.C.", "Gamma F.C.", (3, 1)),
        ("Epsilon F.C.", "Beta F.C.", (0, 1)),
    ]


def _fb(day: str, home: str, away: str, score: str) -> str:
    return (
        f'<div class="footballbox"><div class="fdate"><span class="dtstart">{day}</span></div>'
        f'<table class="fevent"><tbody><tr><th class="fhome">{home}</th><th class="fscore">{score}</th>'
        f'<th class="faway">{away}</th></tr></tbody></table></div>'
    )


def test_box_teams_skip_flags_and_resolve_unlinked_names() -> None:
    flag = '<span class="flagicon"><a href="./Made-up_Football_Federation" title="Made-up Football Federation"><img alt="X"/></a></span>'
    html = (
        _fb("2031-02-01", f'{flag} <a href="./Alpha_F.C." title="Alpha F.C.">Alpha</a>', f'<a href="./Beta_F.C." title="Beta F.C.">Beta</a> {flag}', "1–0")
        + _fb("2031-02-08", f"Beta {flag}", f"{flag} Alpha", "2–2")  # linked only on first mention
    )
    assert [(b.home, b.away, b.score) for b in parse_match_boxes(html)] == [
        ("Alpha F.C.", "Beta F.C.", (1, 0)),
        ("Beta F.C.", "Alpha F.C.", (2, 2)),
    ]


def test_box_day_reads_us_style_dates() -> None:
    html = _fb("x", '<a href="./Alpha_F.C." title="Alpha F.C.">Alpha</a>', '<a href="./Beta_F.C." title="Beta F.C.">Beta</a>', "0–0")
    html = html.replace('<span class="dtstart">x</span>', "July 29, 2015")
    assert [b.day for b in parse_match_boxes(html)] == [date(2015, 7, 29)]


def test_unlinked_names_resolve_by_flag_and_never_by_guess() -> None:
    """Two clubs called `Nacional` on one page: an unlinked one resolves only through its flag."""

    def flag(country: str) -> str:
        return f'<span class="flagicon"><a href="./{country}" title="{country}"><img alt="{country}"/></a></span>'

    def club(name: str, title: str, country: str) -> str:
        return f'<a href="./{title.replace(" ", "_")}" title="{title}">{name}</a> {flag(country)}'

    html = (
        _fb("2031-02-01", club("Nacional", "Club Nacional", "Paraguay"), club("Aucas", "S.D. Aucas", "Ecuador"), "0–1")
        + _fb("2031-02-02", club("Nacional", "Club Nacional de Football", "Uruguay"), club("Cabello", "Academia Puerto Cabello", "Venezuela"), "2–0")
        + _fb("2031-02-08", f"Nacional {flag('Uruguay')}", f"{flag('Venezuela')} Cabello", "2–0")  # the Uruguayan club
        + _fb("2031-02-09", "Nacional", f"{flag('Ecuador')} Aucas", "3–0")  # no flag: either club
    )
    assert [(b.home, b.away) for b in parse_match_boxes(html)] == [
        ("Club Nacional", "S.D. Aucas"),
        ("Club Nacional de Football", "Academia Puerto Cabello"),
        ("Club Nacional de Football", "Academia Puerto Cabello"),
    ]


def test_box_scores_written_with_a_minus_sign() -> None:
    """Some boxes use U+2212 (`2−0`) where the style guide asks for an en dash."""
    html = _fb("2012-07-04", '<a href="./Alpha_F.C." title="Alpha F.C.">Alpha</a>', '<a href="./Beta_F.C." title="Beta F.C.">Beta</a>', "2−0")
    assert [b.score for b in parse_match_boxes(html)] == [(2, 0)]


def _standings_html(rows: list[tuple[str, ...]], header: str = "Pos|Team v t e|Pld|W|D|L|GF|GA|GD|Pts|Qualification") -> str:
    head = "".join(f"<th>{h}</th>" for h in header.split("|"))
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="wikitable"><tbody><tr>{head}</tr>{body}</tbody></table>'


def _club(title: str, note: str = "") -> str:
    flag = '<span class="flagicon"><a href="./Made-up_Federation" title="Made-up Federation"><img alt="X"/></a></span>'
    return f'{flag} <a href="./{title.replace(" ", "_")}" title="{title}">{title.split()[0]}</a>{note}'


def test_standings_tables_map_columns_and_skip_flags_and_notes() -> None:
    html = _standings_html(
        [
            ("1", _club("Alpha F.C.", " (C)"), "38", "28", "7", "3", "96", "34", "+62", "91<sup>[a]</sup>", "Champions League"),
            ("2", _club("Beta F.C."), "38", "28", "5", "5", "91", "29", "+62", "89", ""),
        ]
    ) + _standings_html([("x", "y")], header="Rank|Player|Goals")  # not a standings table
    [table] = parse_standings(html)
    assert table[0] == StandingsLine(1, "Alpha F.C.", 38, 28, 7, 3, 96, 34, 91)
    assert table[1].team == "Beta F.C." and table[1].points == 89


def test_standings_columns_by_name_and_negative_points() -> None:
    html = _standings_html([("20", _club("Gamma F.C."), "−4", "38", "10", "9", "19", "50", "60")], header="Pos|Team|Pts|Pld|W|D|L|F|A")
    [[line]] = parse_standings(html)
    assert (line.position, line.points, line.played, line.goals_for, line.goals_against) == (20, -4, 38, 50, 60)


def test_same_table_in_two_articles_counts_once() -> None:
    page = _standings_html([("1", _club("Alpha F.C."), "3", "3", "0", "0", "5", "0", "+5", "9")])
    assert len(merge_standings([parse_standings(page), parse_standings(page)])) == 1


def test_standings_without_a_position_column_use_row_order() -> None:
    html = _standings_html(
        [(_club("Alpha F.C."), "3", "2", "1", "0", "3", "0", "+3", "7"), (_club("Beta F.C."), "3", "1", "1", "1", "2", "2", "0", "4")],
        header="Team v t e|Pld|W|D|L|GF|GA|GD|Pts",
    )
    [table] = parse_standings(html)
    assert [(line.position, line.team) for line in table] == [(1, "Alpha F.C."), (2, "Beta F.C.")]


async def test_page_cache_keeps_recent_pages_only() -> None:
    """A run reads about a thousand articles; only recent ones stay in memory."""
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.raw_path.decode())
        return httpx.Response(200, text="<html></html>")

    async with client_with(httpx.MockTransport(handler)) as wiki:
        await wiki.results_grid("Page 0")
        await wiki.results_grid("Page 0")  # cached
        for i in range(1, PAGE_CACHE_SIZE + 1):
            await wiki.results_grid(f"Page {i}")
        await wiki.results_grid("Page 0")  # evicted by then: fetched again
    assert len(requested) == PAGE_CACHE_SIZE + 2
