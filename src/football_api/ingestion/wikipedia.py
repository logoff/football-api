"""English Wikipedia as a verification reference: the results grid of a league season article.

Reads the *rendered* article (REST `page/html`), because the grid's wikitext lives in
different places from season to season while the `sports results` module always renders
the same square table (design D1). Nothing read here is stored; callers only compare.
"""

import asyncio
import json
from collections import OrderedDict
import re
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date
from importlib.metadata import version
from typing import Any, cast
from urllib.parse import quote, unquote

import httpx
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

from football_api.domain.enums import CardKind

USER_AGENT = f"football-api/{version('football-api')} (+https://github.com/logoff/football-api)"
TIMEOUT = 20.0
MAX_RETRY_AFTER = 30.0
TITLES_PER_QUERY = 50
PAGE_CACHE_SIZE = 16  # pages kept per client; a season reads at most about a dozen
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


Minute = tuple[int, int | None]  # minute, added minute


@dataclass(frozen=True)
class LineupRow:
    """One player of a line-up table (verify-match-events D1). Compared, never stored."""

    name: str
    number: int | None  # the shirt number; tables before 1950 have none
    starter: bool
    on: Minute | None = None  # came on (`{{subon}}`); a substitute without it stayed on the bench
    off: Minute | None = None  # went off (`{{suboff}}`)
    cards: tuple[tuple[CardKind, Minute | None], ...] = ()

    @property
    def played(self) -> bool:
        return self.starter or self.on is not None


@dataclass(frozen=True)
class MatchBox:
    """One match of a cup article: a "Football box collapsible" or a "Football box"."""

    day: date | None
    home: str  # article title of the home club
    away: str
    score: tuple[int, int] | None  # full time including extra time; None for w/o, void, bye, unplayed
    shootout: tuple[int, int] | None = None
    awarded: bool = False
    # The line-up table after the box, home side first; None when there is none.
    lineups: tuple[tuple[LineupRow, ...], tuple[LineupRow, ...]] | None = field(default=None, compare=False)


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


_MINUTE = re.compile(r"^\s*(\d+)(?:\s*\+\s*(\d+))?")
_CAPTAIN = re.compile(r"\(\s*c\s*\)", re.I)
_CARD_TEMPLATES = {"yel", "sent off", "sentoff", "sent-off"}
_SUB_TEMPLATES = {"suboff", "subon"}


def _minute(wikitext: str | None) -> Minute | None:
    m = _MINUTE.match(wikitext or "")
    return (int(m[1]), int(m[2]) if m[2] else None) if m else None


def _obj(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _templates(row: Tag) -> list[tuple[str, dict[str, str], str | None]]:
    """The templates rendered in a row, from Parsoid's `data-mw`: (name, parameters, `about` id)."""
    out: list[tuple[str, dict[str, str], str | None]] = []
    for el in row.select("[data-mw]"):
        try:
            mw = _obj(json.loads(str(el["data-mw"])))
        except ValueError:
            continue
        parts = cast(list[object], mw.get("parts")) if isinstance(mw.get("parts"), list) else []
        for part in parts:
            template = _obj(_obj(part).get("template"))
            if not template:
                continue
            name = str(_obj(template.get("target")).get("wt", "")).strip().lower()
            params = {key: str(_obj(value).get("wt", "")) for key, value in _obj(template.get("params")).items()}
            about = el.get("about")
            out.append((name, params, about if isinstance(about, str) else None))
    return out


def _row_cards(templates: list[tuple[str, dict[str, str], str | None]]) -> list[tuple[CardKind, Minute | None]]:
    """`{{yel|15}}` is a booking. `{{sent off|N|…}}` is a dismissal after N yellow cards, their
    minutes first and the dismissal's last: `{{sent off|0|80}}` a red card, `{{sent off|2|54|74}}`
    a second yellow at 74 after a booking at 54, `{{sent off|1|30|80}}` a booking and a red."""
    cards: list[tuple[CardKind, Minute | None]] = []
    for name, params, _ in templates:
        if name == "yel":
            cards.append((CardKind.YELLOW, _minute(params.get("1"))))
        elif name in _CARD_TEMPLATES:
            yellows = params.get("1", "0").strip()
            if yellows == "2":
                cards += [(CardKind.YELLOW, _minute(params.get("2"))), (CardKind.SECOND_YELLOW, _minute(params.get("3")))]
            elif yellows == "1":
                cards += [(CardKind.YELLOW, _minute(params.get("2"))), (CardKind.RED, _minute(params.get("3")))]
            else:
                cards.append((CardKind.RED, _minute(params.get("2"))))
    return cards


def _text_outside(cell: Tag, abouts: set[str]) -> str:
    """A cell's text without the output of the given templates (a booking's `15'`)."""
    parts: list[str] = []
    for text in cell.find_all(string=True):
        assert isinstance(text, NavigableString)
        if not any(isinstance(p.get("about"), str) and p.get("about") in abouts for p in text.parents if p is not cell):
            parts.append(str(text))
    return " ".join(" ".join(parts).split())


def _side_lineup(table: Tag) -> tuple[LineupRow, ...]:
    """A side table: `position | number | player | cards | substitution` rows (no number before
    1950), then a `Substitutions:` header and the substitutes, then `Manager:`."""
    rows: list[LineupRow] = []
    starters = True
    body = table.find("tbody", recursive=False)
    for tr in (body or table).find_all("tr", recursive=False):
        heading = tr.get_text(" ", strip=True).lower()
        if heading.startswith(("substitut", "subs")):
            starters = False
            continue
        if heading.startswith(("manager", "coach", "head coach")):
            break
        cells: list[Tag] = list(tr.find_all("td", recursive=False))
        if len(cells) < 2:
            continue
        templates = _templates(tr)
        abouts = {a for n, _, a in templates if a and (n in _CARD_TEMPLATES or n in _SUB_TEMPLATES)}
        number: int | None = None
        name = ""
        for cell in cells[1:]:
            text = _text_outside(cell, abouts)
            if text.isdigit() and number is None and not name:
                number = int(text)
            elif text:
                name = _CAPTAIN.sub("", text).strip()
                break
        if not re.search(r"[^\W\d_]", name):  # `—`: a card for someone not on the pitch
            continue
        subs = {n: _minute(p.get("1")) for n, p, _ in templates if n in _SUB_TEMPLATES}
        rows.append(LineupRow(name, number, starters, subs.get("subon"), subs.get("suboff"), tuple(_row_cards(templates))))
    return tuple(rows)


def _is_gk_row(cell: Tag) -> bool:
    return cell.get_text(strip=True) == "GK"


def _lineups_after(node: Tag, stop: Tag | None) -> tuple[tuple[LineupRow, ...], tuple[LineupRow, ...]] | None:
    """The line-up table that follows a match box, before the next box: the first table holding two
    side tables with a `GK` row."""
    table = node
    while (table := table.find_next("table")) is not None:
        if stop is not None and (table is stop or stop in table.parents):
            return None
        if node in table.parents:
            continue
        if table.find_parent(class_="footballbox") is not None:
            return None
        # The innermost tables holding a `GK` row: some pages wrap a side table in another one.
        sides = [t for t in table.find_all("table") if any(_is_gk_row(td) and td.find_parent("table") is t for td in t.find_all("td"))]
        if len(sides) >= 2:
            home, away = _side_lineup(sides[0]), _side_lineup(sides[1])
            return (home, away) if home and away else None
    return None


def parse_match_boxes(html: str) -> list[MatchBox]:
    """Every match box in a cup article, in page order, with the line-up table that follows it."""
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
    for i, node in enumerate(nodes):
        box = _collapsible_box(node, linked) if node.name == "table" else _football_box(node, linked)
        if box is not None:
            if node.name == "div":
                box = replace(box, lineups=_lineups_after(node, nodes[i + 1] if i + 1 < len(nodes) else None))
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
        if "redlink=1" in href:  # an article that doesn't exist
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


def _detail(box: MatchBox) -> int:
    """How much a box's line-up table records: -1 without one, else its cards and substitutions."""
    if box.lineups is None:
        return -1
    return sum(len(r.cards) + (r.on is not None) + (r.off is not None) for side in box.lineups for r in side)


def merge_boxes(groups: Iterable[list[MatchBox]]) -> list[MatchBox]:
    """One box per (date, home, away): the season article first, then sub-articles (design D2).
    The line-ups come from the copy that records the most (verify-match-events D1): a knockout
    stage article can repeat the final's line-ups without its cards, which the final's own
    article has."""
    seen: dict[tuple[date | None, str, str], int] = {}
    out: list[MatchBox] = []
    for boxes in groups:
        for box in boxes:
            key = (box.day, box.home, box.away)
            if key not in seen:
                seen[key] = len(out)
                out.append(box)
            elif _detail(box) > _detail(out[seen[key]]):
                out[seen[key]] = replace(out[seen[key]], lineups=box.lineups)
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
        # Recent pages only: a season's match boxes and standings read the same articles one after
        # the other. Keeping every page of a run (about a thousand) ran the nightly job out of memory.
        self._pages: OrderedDict[str, tuple[str, int | None]] = OrderedDict()  # title → (html, revision)
        self._recording: dict[str, int] | None = None
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

    @contextmanager
    def record_pages(self) -> Generator[dict[str, int]]:
        """Collect the title and revision ID of every page read inside the block, cached or not."""
        self._recording = {}
        try:
            yield self._recording
        finally:
            self._recording = None

    async def _page_html(self, title: str) -> str:
        if title in self._pages:
            self._pages.move_to_end(title)
            html, revision = self._pages[title]
        else:
            resp = await self._get(f"{self._rest}/page/html/{quote(title.replace(' ', '_'), safe='')}")
            if resp.status_code != 200:
                raise WikipediaUnavailable(f"{title}: HTTP {resp.status_code}")
            # The REST API names the revision it rendered, the action API's `lastrevid`.
            header = resp.headers.get("content-revision-id", "")
            html, revision = resp.text, int(header) if header.isdigit() else None
            self._pages[title] = (html, revision)
            while len(self._pages) > PAGE_CACHE_SIZE:
                self._pages.popitem(last=False)
        if self._recording is not None and revision is not None:
            self._recording[title] = revision
        return html

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

    async def _query(self, titles: Iterable[str], prop: dict[str, str]) -> list[tuple[str, dict[str, Any]]]:
        """Each requested title with the page it ends at after normalisation and redirects, in
        batches; titles with no page are left out."""
        wanted = sorted(set(titles))
        found: list[tuple[str, dict[str, Any]]] = []
        for i in range(0, len(wanted), TITLES_PER_QUERY):
            batch = wanted[i : i + TITLES_PER_QUERY]
            resp = await self._get(
                self._api,
                {"action": "query", "format": "json", "formatversion": "2", "redirects": "1", "titles": "|".join(batch), **prop},
            )
            if resp.status_code != 200:
                raise WikipediaUnavailable(f"{prop['prop']}: HTTP {resp.status_code}")
            query = cast(dict[str, Any], resp.json().get("query", {}))
            hops: dict[str, str] = {}
            for key in ("normalized", "redirects"):
                for hop in cast(list[dict[str, str]], query.get(key, [])):
                    hops[hop["from"]] = hop["to"]
            page_of = {
                cast(str, page["title"]): page
                for page in cast(list[dict[str, Any]], query.get("pages", []))
                if not page.get("missing") and not page.get("invalid")
            }
            for title in batch:
                final, seen = title, {title}
                while final in hops and hops[final] not in seen:
                    final = hops[final]
                    seen.add(final)
                if final in page_of:
                    found.append((title, page_of[final]))
        return found

    async def qids(self, titles: Iterable[str]) -> dict[str, str]:
        """Map article titles to Wikidata QIDs, following normalisation and redirects."""
        return {
            title: cast(str, page["pageprops"]["wikibase_item"])
            for title, page in await self._query(titles, {"prop": "pageprops", "ppprop": "wikibase_item"})
            if "wikibase_item" in cast(dict[str, Any], page.get("pageprops", {}))
        }

    async def revisions(self, titles: Iterable[str]) -> dict[str, int]:
        """The current revision ID of each title that exists, following normalisation and redirects."""
        return {
            title: cast(int, page["lastrevid"])
            for title, page in await self._query(titles, {"prop": "info"})
            if "lastrevid" in page
        }
