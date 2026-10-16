"""English Wikipedia as a verification reference: the results grid of a league season article.

Reads the *rendered* article (REST `page/html`), because the grid's wikitext lives in
different places from season to season while the `sports results` module always renders
the same square table (design D1). Nothing read here is stored; callers only compare.
"""

import asyncio
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from importlib.metadata import version
from typing import Any, cast
from urllib.parse import quote, unquote

import httpx
from bs4 import BeautifulSoup, Tag

USER_AGENT = f"football-api/{version('football-api')} (+https://github.com/logoff/football-api)"
TIMEOUT = 20.0
MAX_RETRY_AFTER = 30.0
TITLES_PER_QUERY = 50
_SCORE = re.compile(r"^(\d+)\s*[–−-]\s*(\d+)$")
_BOX_SCORE = re.compile(r"^(\d+)\s*[–−-]\s*(\d+)\b")
_BOX_PENS = re.compile(r"\(\s*(\d+)\s*[–−-]\s*(\d+)\s*p\s*\)")
_BOX_AWARDED = re.compile(r"\bawd\.|\bawarded\b", re.I)


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


@dataclass(frozen=True)
class MatchBox:
    """One match of a cup article: a "Football box collapsible" or a "Football box"."""

    day: date | None
    home: str  # article title of the home club
    away: str
    score: tuple[int, int] | None  # full time including extra time; None for w/o, void, bye, unplayed
    shootout: tuple[int, int] | None = None
    awarded: bool = False


_MONTHS = {m: i for i, m in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), 1
)}
_TEXT_DATE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b")
_US_TEXT_DATE = re.compile(r"\b([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})\b")  # `July 29, 2015`


def _box_day(node: Tag | None) -> date | None:
    """The box's date: the hidden ISO `dtstart` when the article uses {{Start date}}, else
    `14 November 2023` or `November 14, 2023`."""
    if node is None:
        return None
    stamp = node.select_one(".dtstart")
    try:
        if stamp:
            return date.fromisoformat(stamp.get_text(strip=True)[:10])
        text = node.get_text(" ", strip=True)
        m = _TEXT_DATE.search(text)
        if m and m[2].lower() in _MONTHS:
            return date(int(m[3]), _MONTHS[m[2].lower()], int(m[1]))
        m = _US_TEXT_DATE.search(text)
        if m and m[1].lower() in _MONTHS:
            return date(int(m[3]), _MONTHS[m[1].lower()], int(m[2]))
    except ValueError:
        pass
    return None


def _box_result(cell_text: str, shootout_text: str | None = None) -> tuple[tuple[int, int] | None, tuple[int, int] | None, bool]:
    m = _BOX_SCORE.match(cell_text)
    if m is None:
        return None, None, False
    pens = _BOX_PENS.search(cell_text) or (_BOX_SCORE.match(shootout_text) if shootout_text else None)
    return (int(m[1]), int(m[2])), (int(pens[1]), int(pens[2])) if pens else None, bool(_BOX_AWARDED.search(cell_text))


def _cell_name(cell: Tag) -> str:
    """A team cell's visible name without a `(7)` tier note: `Arsenal`."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", cell.get_text(" ", strip=True)).strip()


def _cell_flag(cell: Tag) -> str | None:
    """The country or federation a cell's flag icon links to: it tells apart two clubs called `Nacional`."""
    link = cell.select_one(".flagicon a[href]")
    return _anchor_title(link) if link is not None else None


# (visible name, flag) → the articles cells showing them link to.
Linked = dict[tuple[str, str | None], set[str]]


def _team_title(cell: Tag, linked: Linked) -> str | None:
    """The club or team a box cell links to, skipping flag icons (a club's flag links to its
    federation, `Croatian Football Federation`). A cell without a link uses the article its visible
    name and flag link to elsewhere on the page, as Wikipedia links a club only on first mention;
    a name that links to more than one article is left unresolved."""
    for link in cell.find_all("a", href=True):
        if not link.get_text(strip=True) or link.find_parent(class_="flagicon"):
            continue
        return _anchor_title(link)
    name = _cell_name(cell)
    titles = linked.get((name, _cell_flag(cell))) or {t for (n, _), ts in linked.items() if n == name for t in ts}
    return next(iter(titles)) if len(titles) == 1 else None


def _anchor_title(link: Tag) -> str | None:
    title = link.get("title")
    if isinstance(title, str) and title:
        return title
    href = link.get("href")
    if isinstance(href, str) and href.startswith("./"):
        return unquote(href[2:].split("#", 1)[0]).replace("_", " ")
    return None


def _collapsible_box(table: Tag, linked: Linked) -> MatchBox | None:
    row = table.find("tr")
    cells: list[Tag] = list(row.find_all("td", recursive=False)) if isinstance(row, Tag) else []
    if len(cells) < 4:
        return None
    home, away = _team_title(cells[1], linked), _team_title(cells[3], linked)
    if home is None or away is None:
        return None
    score, shootout, awarded = _box_result(cells[2].get_text(" ", strip=True))
    return MatchBox(_box_day(cells[0]), home, away, score, shootout, awarded)


def _football_box(box: Tag, linked: Linked) -> MatchBox | None:
    table = box.select_one("table.fevent")
    home_cell, score_cell, away_cell = (box.select_one(c) for c in (".fhome", ".fscore", ".faway"))
    if table is None or home_cell is None or score_cell is None or away_cell is None:
        return None
    home, away = _team_title(home_cell, linked), _team_title(away_cell, linked)
    if home is None or away is None:
        return None
    shootout_text = None
    rows = table.find_all("tr")
    for i, tr in enumerate(rows[:-1]):
        if tr.get_text(strip=True).lower().startswith("penalties"):
            middle = _cells(rows[i + 1])
            shootout_text = middle[1].get_text(" ", strip=True) if len(middle) == 3 else None
    score, shootout, awarded = _box_result(score_cell.get_text(" ", strip=True), shootout_text)
    return MatchBox(_box_day(box), home, away, score, shootout, awarded)


def parse_match_boxes(html: str) -> list[MatchBox]:
    """Every match box in a cup article, in page order."""
    soup = BeautifulSoup(html, "html.parser")
    for note in soup.find_all("sup"):
        note.decompose()
    nodes = soup.select("table.tmpl-football-box-collapsible, div.footballbox")
    linked: Linked = {}  # from the cells that do link
    for node in nodes:
        cells = node.select(".fhome, .faway") if node.name == "div" else node.select("td.vcard")
        for cell in cells:
            title = _team_title(cell, {})
            if title:
                linked.setdefault((_cell_name(cell), _cell_flag(cell)), set()).add(title)
    boxes: list[MatchBox] = []
    for node in nodes:
        box = _collapsible_box(node, linked) if node.name == "table" else _football_box(node, linked)
        if box is not None:
            boxes.append(box)
    return boxes


# Sub-articles a season article links that hold no reference matches for us (design D1). Qualifying
# sub-articles are read only for seasons that store qualifying matches (`… qualifying stages`);
# `UEFA Euro 2024 qualifying` or `2026 FIFA World Cup qualification` are other tournaments.
_QUALIFYING = re.compile(r"qualif", re.I)
_SKIP_SUBARTICLE = re.compile(
    r"qualification|squad|femenin|futsal|\bbids?\b|statistic|broadcast|official|controvers|seeding|ceremon|disciplin|record",
    re.I,
)


def page_title(html: str) -> str | None:
    title = BeautifulSoup(html, "html.parser").find("title")
    return title.get_text(strip=True) if isinstance(title, Tag) else None


def parse_subarticle_titles(html: str, title: str, *, qualifying: bool = False) -> list[str]:
    """Linked articles whose titles extend the season article's own (`… Group A`, `… knockout phase`),
    minus qualifying, squads, other editions and non-match topics; in link order, no duplicates."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for link in soup.select("a[href]"):
        href = link.get("href")
        if not isinstance(href, str) or not href.startswith("./"):
            continue
        target = unquote(href[2:].split("#", 1)[0]).replace("_", " ")
        suffix = target[len(title) :]
        if not target.startswith(title + " ") or _SKIP_SUBARTICLE.search(suffix) or target in out:
            continue
        if qualifying or not _QUALIFYING.search(suffix):
            out.append(target)
    return out


@dataclass(frozen=True)
class StandingsLine:
    """One row of a Wikipedia standings table. Compared, never stored (verify-standings D2)."""

    position: int
    team: str  # the linked article's title
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    points: int


StandingsTable = list[StandingsLine]

# Header text → field; tables name columns slightly differently across eras.
_STANDINGS_COLUMNS = {
    "pos": "position", "team": "team", "pld": "played", "p": "played", "gp": "played", "mp": "played",
    "w": "won", "d": "drawn", "l": "lost", "gf": "goals_for", "f": "goals_for", "ga": "goals_against",
    "a": "goals_against", "pts": "points",
}  # fmt: skip
_INT = re.compile(r"^[−-]?\d+")


def _header_key(cell: Tag) -> str:
    # `Team v t e`: the navbox links after the header word don't count.
    words = cell.get_text(" ", strip=True).split()
    return words[0].lower().rstrip(".") if words else ""


def parse_standings(html: str) -> list[StandingsTable]:
    """Every standings table in an article: tables whose header names `Team`, `Pld` and `Pts`.
    Older tables have no `Pos` column; their row order is the position."""
    soup = BeautifulSoup(html, "html.parser")
    for note in soup.find_all("sup"):
        note.decompose()
    tables: list[StandingsTable] = []
    for table in soup.select("table"):
        rows = [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]
        if not rows:
            continue
        header = [_STANDINGS_COLUMNS.get(_header_key(c)) for c in _cells(rows[0])]
        if not {"team", "played", "points"} <= set(header):
            continue
        lines: StandingsTable = []
        for tr in rows[1:]:
            cells = _cells(tr)
            if len(cells) < len([h for h in header if h]):
                continue
            values: dict[str, object] = {}
            for field, cell in zip(header, cells, strict=False):
                if field == "team":
                    values["team"] = _team_title(cell, {})
                elif field:
                    m = _INT.match(cell.get_text(" ", strip=True).replace("−", "-"))
                    values[field] = int(m[0].replace("−", "-")) if m else None
            if "position" not in header:
                values["position"] = len(lines) + 1
            if values.get("team") is None or any(values.get(f) is None for f in ("position", "played", "points")):
                continue
            lines.append(
                StandingsLine(
                    position=cast(int, values["position"]),
                    team=cast(str, values["team"]),
                    played=cast(int, values["played"]),
                    won=cast(int, values.get("won") or 0),
                    drawn=cast(int, values.get("drawn") or 0),
                    lost=cast(int, values.get("lost") or 0),
                    goals_for=cast(int, values.get("goals_for") or 0),
                    goals_against=cast(int, values.get("goals_against") or 0),
                    points=cast(int, values["points"]),
                )
            )
        if lines:
            tables.append(lines)
    return tables


def merge_standings(groups: Iterable[list[StandingsTable]]) -> list[StandingsTable]:
    """Tables by set of teams, first seen first: a group table in the season article and in its
    group sub-article counts once."""
    seen: set[frozenset[str]] = set()
    out: list[StandingsTable] = []
    for tables in groups:
        for table in tables:
            key = frozenset(line.team for line in table)
            if key not in seen:
                seen.add(key)
                out.append(table)
    return out


def merge_boxes(groups: Iterable[list[MatchBox]]) -> list[MatchBox]:
    """One box per (date, home, away): the season article first, then sub-articles (design D2)."""
    seen: set[tuple[date | None, str, str]] = set()
    out: list[MatchBox] = []
    for boxes in groups:
        for box in boxes:
            key = (box.day, box.home, box.away)
            if key not in seen:
                seen.add(key)
                out.append(box)
    return out


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
        self._pages: dict[str, str] = {}  # one run reads each article once (match boxes, standings)
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

    async def _page_html(self, title: str) -> str:
        if title in self._pages:
            return self._pages[title]
        resp = await self._get(f"{self._rest}/page/html/{quote(title.replace(' ', '_'), safe='')}")
        if resp.status_code != 200:
            raise WikipediaUnavailable(f"{title}: HTTP {resp.status_code}")
        self._pages[title] = resp.text
        return resp.text

    async def _season_pages(self, title: str, *, qualifying: bool = False) -> list[str]:
        """The season article, then the sub-articles it links (groups, knockout phase, qualifying
        stages when asked). Missing article → unavailable; a missing sub-article is skipped."""
        html = await self._page_html(title)
        pages = [html]
        for sub in parse_subarticle_titles(html, page_title(html) or title, qualifying=qualifying):
            try:
                pages.append(await self._page_html(sub))
            except WikipediaUnavailable:
                continue
        return pages

    async def results_grid(self, title: str) -> ResultsGrid | None:
        """The article's results grid; None when the article has none. Missing article → unavailable."""
        return parse_results_grid(await self._page_html(title))

    async def match_boxes(self, title: str, *, qualifying: bool = False) -> list[MatchBox]:
        """The match boxes of a cup or tournament season: the article's own, then those of the
        sub-articles it links (groups, knockout phase, and qualifying stages when asked), each match once. Missing article → unavailable;
        a missing sub-article is skipped."""
        return merge_boxes(parse_match_boxes(page) for page in await self._season_pages(title, qualifying=qualifying))

    async def standings(self, title: str, *, qualifying: bool = False) -> list[StandingsTable]:
        """The standings tables of a season article and its sub-articles, each set of teams once."""
        return merge_standings(parse_standings(page) for page in await self._season_pages(title, qualifying=qualifying))

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
