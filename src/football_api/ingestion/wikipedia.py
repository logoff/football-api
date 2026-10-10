"""English Wikipedia as a verification reference: the results grid of a league season article.

Reads the *rendered* article (REST `page/html`), because the grid's wikitext lives in
different places from season to season while the `sports results` module always renders
the same square table (design D1). Nothing read here is stored; callers only compare.
"""

import asyncio
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any, cast
from urllib.parse import quote, unquote

import httpx
from bs4 import BeautifulSoup, Tag

USER_AGENT = f"football-api/{version('football-api')} (+https://github.com/logoff/football-api)"
TIMEOUT = 20.0
MAX_RETRY_AFTER = 30.0
TITLES_PER_QUERY = 50
_SCORE = re.compile(r"^(\d+)\s*[–-]\s*(\d+)$")


class WikipediaUnavailable(Exception):
    pass


@dataclass(frozen=True)
class GridCell:
    home: str  # article title of the home club
    away: str
    score: tuple[int, int] | None  # None: not played yet, or a placeholder


@dataclass(frozen=True)
class ResultsGrid:
    teams: list[str]
    cells: list[GridCell]


def _link_title(cell: Tag) -> str | None:
    link = cell.find("a", href=True)
    if not isinstance(link, Tag):
        return None
    title = link.get("title")
    if isinstance(title, str) and title:
        return title
    href = link.get("href")
    if isinstance(href, str) and href.startswith("./"):
        return unquote(href[2:].split("#", 1)[0]).replace("_", " ")
    return None


def _cells(row: Tag) -> list[Tag]:
    return list(row.find_all(["th", "td"], recursive=False))


def _score(cell: Tag) -> tuple[int, int] | None:
    for note in cell.find_all("sup"):
        note.decompose()
    m = _SCORE.match(cell.get_text(" ", strip=True))
    return (int(m[1]), int(m[2])) if m else None


def _grid(table: Tag) -> ResultsGrid | None:
    rows = list(table.find_all("tr"))
    if len(rows) < 3:
        return None
    columns = [_link_title(c) for c in _cells(rows[0])[1:]]
    if len(columns) < 2 or any(t is None for t in columns):
        return None
    away_titles = cast(list[str], columns)
    body = [(row, _cells(row)) for row in rows[1:]]
    body = [(row, cells) for row, cells in body if cells and _link_title(cells[0])]
    if len(body) != len(away_titles) or any(len(cells) != len(away_titles) + 1 for _, cells in body):
        return None
    grid: list[GridCell] = []
    for _, cells in body:
        home = cast(str, _link_title(cells[0]))
        for away, cell in zip(away_titles, cells[1:], strict=True):
            if away != home:
                grid.append(GridCell(home, away, _score(cell)))
    if not any(c.score for c in grid):
        return None
    return ResultsGrid(teams=away_titles, cells=grid)


def parse_results_grid(html: str) -> ResultsGrid | None:
    """The first square team-by-team results table in the page, or None if there is none."""
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        if grid := _grid(table):
            return grid
    return None


class WikipediaClient:
    """Polite access: project User-Agent, short timeouts, one retry on 429/5xx (design D6)."""

    def __init__(
        self,
        *,
        rest: str,
        api: str,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self._rest, self._api, self._sleep = rest.rstrip("/"), api, sleep
        self._client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, transport=transport, follow_redirects=True
        )

    async def __aenter__(self) -> "WikipediaClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def _get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        for attempt in (1, 2):
            try:
                resp = await self._client.get(url, params=params)
            except httpx.TransportError as exc:
                raise WikipediaUnavailable(f"{url}: {exc or type(exc).__name__}") from exc
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == 1:
                    try:
                        delay = float(resp.headers.get("Retry-After", "5"))
                    except ValueError:
                        delay = 5.0
                    await self._sleep(min(max(delay, 0.0), MAX_RETRY_AFTER))
                    continue
                raise WikipediaUnavailable(f"{url}: HTTP {resp.status_code}")
            return resp
        raise AssertionError("unreachable")

    async def results_grid(self, title: str) -> ResultsGrid | None:
        """The article's results grid; None when the article has none. Missing article → unavailable."""
        resp = await self._get(f"{self._rest}/page/html/{quote(title.replace(' ', '_'), safe='')}")
        if resp.status_code != 200:
            raise WikipediaUnavailable(f"{title}: HTTP {resp.status_code}")
        return parse_results_grid(resp.text)

    async def qids(self, titles: Iterable[str]) -> dict[str, str]:
        """Map article titles to Wikidata QIDs, following normalisation and redirects."""
        wanted = sorted(set(titles))
        found: dict[str, str] = {}
        for i in range(0, len(wanted), TITLES_PER_QUERY):
            batch = wanted[i : i + TITLES_PER_QUERY]
            resp = await self._get(
                self._api,
                {
                    "action": "query", "format": "json", "formatversion": "2", "redirects": "1",
                    "prop": "pageprops", "ppprop": "wikibase_item", "titles": "|".join(batch),
                },
            )
            if resp.status_code != 200:
                raise WikipediaUnavailable(f"pageprops: HTTP {resp.status_code}")
            query = cast(dict[str, Any], resp.json().get("query", {}))
            hops: dict[str, str] = {}
            for key in ("normalized", "redirects"):
                for hop in cast(list[dict[str, str]], query.get(key, [])):
                    hops[hop["from"]] = hop["to"]
            qid_of = {
                cast(str, page["title"]): cast(str, page["pageprops"]["wikibase_item"])
                for page in cast(list[dict[str, Any]], query.get("pages", []))
                if "wikibase_item" in cast(dict[str, Any], page.get("pageprops", {}))
            }
            for title in batch:
                final, seen = title, {title}
                while final in hops and hops[final] not in seen:
                    final = hops[final]
                    seen.add(final)
                if final in qid_of:
                    found[title] = qid_of[final]
        return found
