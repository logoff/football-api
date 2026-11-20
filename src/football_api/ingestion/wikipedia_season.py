"""English Wikipedia as a season's source: the match boxes of pinned page revisions
(source-older-seasons-from-wikipedia, design D1–D5), or for a league their results grids
(la-liga-history-from-wikipedia D4).

Unlike `wikipedia.py`'s verification reads, what is read here is stored and served, under
CC BY-SA 4.0 (season-sources). Each revision and the QIDs of the clubs it links are fetched once
and kept under the sources directory, so a season whose pins haven't moved needs no network.
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from football_api.domain.enums import DecidedBy, License, MatchStatus, Publisher
from football_api.ingestion.openfootball.text_parser import ParsedMatch, ParsedScore, normalize_stage
from football_api.ingestion.seeds import SeasonSource, TeamSeed, WikipediaPin
from football_api.ingestion.wikipedia import MatchBox, SeasonGrid, merge_boxes, parse_match_boxes, parse_season_grids

WIKIPEDIA = "wikipedia"  # external_ref source of the seasons and matches read here
REVISION_URL = "https://en.wikipedia.org/w/index.php?oldid={}"

# Headings that hold matches without naming their stage: legs, replays and section wrappers. The
# stage comes from the heading above them (`Quarter-finals / Play-off` is a quarter-final).
_NOT_A_STAGE = {
    "first leg", "second leg", "matches", "groups", "play-off", "play-offs", "replay", "replays",
    "tie-breaker", "tie-breakers", "knockout phase", "knockout stage", "summary",
    # Wrappers of rounds, never a round: `Final phase / Third round` is a third round, not a final
    # (cup-winners-cup-and-uefa-cup-from-wikipedia D2).
    "final phase", "tournament phase", "qualifying phase",
}


class WikipediaSourceError(Exception):
    pass


class RevisionClient(Protocol):
    async def revision_html(self, title: str, revision: int) -> str: ...
    async def qids(self, titles: Iterable[str]) -> dict[str, str]: ...


class RevisionStore:
    """Pinned revisions and the QIDs of the clubs they link, fetched once and kept under `cache` (D2, D5)."""

    def __init__(self, cache: Path, client: RevisionClient) -> None:
        self._cache, self._client = cache, client

    async def html(self, pin: WikipediaPin) -> str:
        path = self._cache / f"{pin.revision}.html"
        if path.is_file():
            return path.read_text(encoding="utf-8")
        html = await self._client.revision_html(pin.title, pin.revision)
        self._write(path, html)
        return html

    async def qids(self, pin: WikipediaPin, titles: set[str]) -> dict[str, str]:
        """Title → QID for the club articles a revision links. Looked up live once (a title may
        redirect), then cached next to the revision so the season stays reproducible."""
        path = self._cache / f"{pin.revision}.qids.json"
        cached: dict[str, str] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        missing = titles - cached.keys()
        if missing:
            cached |= await self._client.qids(sorted(missing))
            self._write(path, json.dumps(cached, ensure_ascii=False, indent=1, sort_keys=True))
        return {t: cached[t] for t in titles if t in cached}

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)  # a run killed mid-write leaves no truncated file behind


@dataclass(frozen=True)
class WikipediaSeason:
    matches: list[ParsedMatch]  # home and away are Wikidata QIDs
    path: str  # the season article: where errors and match references point
    clubs: dict[str, str]  # QID → the club article that linked it, for error messages


def source_of(src: SeasonSource) -> dict[str, Any]:
    """The season's `source` (season-sources): Wikipedia, CC BY-SA, and each pinned revision."""
    pins = src.wikipedia_source or []
    pages = [{"title": p.title, "url": REVISION_URL.format(p.revision)} for p in pins]
    return {"publisher": Publisher.WIKIPEDIA.value, "license": License.CC_BY_SA.value, "pages": pages}


def round_label(page_suffix: str, heading: tuple[str, ...]) -> str:
    """`first group stage` + ("Groups", "Group A") → `First group stage / Group A`;
    `` + ("Quarter-finals", "Play-off") → `Quarter-finals`."""
    parts = [page_suffix] if page_suffix else []
    parts += [h for h in heading if h.lower() not in _NOT_A_STAGE]
    parts = [p for p in parts if p.lower() not in _NOT_A_STAGE]
    return " / ".join(p[:1].upper() + p[1:] for p in parts)


def _parsed(box: MatchBox, line_no: int, label: str, home: str, away: str) -> ParsedMatch:
    assert box.day is not None
    if box.score is None:  # a walkover or withdrawal: no match result (design D4)
        return ParsedMatch(line_no, label, box.day, None, None, home, away, None, status=MatchStatus.CANCELLED)
    if box.shootout is not None:
        score = ParsedScore(*box.score, DecidedBy.PENALTIES, *box.shootout)
    else:
        score = ParsedScore(*box.score, DecidedBy.EXTRA_TIME if box.extra_time else DecidedBy.REGULAR)
    return ParsedMatch(line_no, label, box.day, None, None, home, away, score, awarded=box.awarded)


def seeded_qids(teams: list[TeamSeed]) -> dict[str, str]:
    """Every QID a box may link → the seeded team's QID: its own, or one of its `reference_wikidata`."""
    out = {ref: t.wikidata for t in teams if t.wikidata for ref in t.reference_wikidata}
    return out | {t.wikidata: t.wikidata for t in teams if t.wikidata}


async def read_season(src: SeasonSource, store: RevisionStore, seeded: dict[str, str]) -> WikipediaSeason:
    """The season's matches from its pinned revisions, each box once, in page order (D3).

    Fails on a box without a date, a heading that names no stage, or a club article without a QID.
    A QID no team is seeded with is left to sync, which fails the season naming the club.
    """
    pins = src.wikipedia_source
    assert pins, f"{src.label} has no Wikipedia pins"
    main = pins[0].title
    skip = {h.lower() for h in src.wikipedia_skip or []}
    skipped: set[str] = set()
    # Headings read as another round label, such as a round robin's `Results` (euro-and-copa-america-from-wikipedia D3).
    rounds = {h.lower(): label for h, label in (src.rounds or {}).items()}
    renamed: set[str] = set()
    labelled: list[list[tuple[MatchBox, WikipediaPin]]] = []
    for pin in pins:
        suffix = pin.title[len(main) :].strip() if pin.title.startswith(main + " ") else ""
        boxes: list[MatchBox] = []
        for b in parse_match_boxes(await store.html(pin)):
            if hit := skip & {h.lower() for h in b.heading}:  # a section the season leaves out (D3)
                skipped |= hit
                continue
            renamed |= rounds.keys() & {h.lower() for h in b.heading}
            heading = tuple(rounds.get(h.lower(), h) for h in b.heading)
            boxes.append(replace(b, heading=(round_label(suffix, heading),)))
        labelled.append([(b, pin) for b in boxes])
    if missing := sorted(h for h in src.wikipedia_skip or [] if h.lower() not in skipped):
        raise WikipediaSourceError(f"{main}: no boxes under the skipped section(s) {', '.join(map(repr, missing))}")
    if missing := sorted(h for h in src.rounds or {} if h.lower() not in renamed):
        raise WikipediaSourceError(f"{main}: no boxes under the renamed section(s) {', '.join(map(repr, missing))}")
    # The page each kept box came from: its first copy, as `merge_boxes` keeps the first.
    pin_of = {(b.day, b.home, b.away): pin for page in reversed(labelled) for b, pin in reversed(page)}
    boxes = merge_boxes([b for b, _ in page] for page in labelled)

    titles: dict[str, set[str]] = {}
    for box in boxes:
        titles.setdefault(pin_of[(box.day, box.home, box.away)].title, set()).update((box.home, box.away))
    # Clubs a box links to an article that doesn't exist take their QID from the seed (D4).
    given = src.wikipedia_qids or {}
    if stale := sorted(set(given) - {t for ts in titles.values() for t in ts}):
        raise WikipediaSourceError(f"{main}: `wikipedia_qids` names {', '.join(map(repr, stale))}, which no box links")
    qid_of: dict[str, str] = dict(given)
    for pin in pins:
        if lookup := titles.get(pin.title, set()) - given.keys():
            qid_of |= await store.qids(pin, lookup)

    # Abandoned and replayed: no result, the replay is the result (euro-and-copa-america-from-wikipedia D4).
    abandoned = {(a.day, a.home, a.away) for a in src.wikipedia_abandoned or []}
    matches: list[ParsedMatch] = []
    clubs: dict[str, str] = {}
    for line_no, box in enumerate(boxes, 1):
        pin = pin_of[(box.day, box.home, box.away)]
        where = f"{pin.title} (revision {pin.revision})"
        if box.day is None:
            raise WikipediaSourceError(f"{where}: {box.home} v {box.away} has no date")
        label = box.heading[0]
        try:
            normalize_stage(label)
        except ValueError:
            raise WikipediaSourceError(f"{where}: heading {label!r} names no stage ({box.home} v {box.away})") from None
        sides: list[str] = []
        for title in (box.home, box.away):
            if title not in qid_of:
                raise WikipediaSourceError(f"{where}: club article {title!r} has no Wikidata QID")
            qid = seeded.get(qid_of[title], qid_of[title])
            clubs.setdefault(qid, title)
            sides.append(qid)
        home, away = sides
        if (box.day, home, away) in abandoned:
            abandoned.discard((box.day, home, away))
            matches.append(ParsedMatch(line_no, label, box.day, None, None, home, away, None, status=MatchStatus.CANCELLED))
            continue
        matches.append(_parsed(box, line_no, label, *sides))
    if abandoned:
        listed = ", ".join(f"{home} v {away} on {day}" for day, home, away in sorted(abandoned))
        raise WikipediaSourceError(f"{main}: `wikipedia_abandoned` lists {listed}, which no box holds")
    return WikipediaSeason(matches, main, clubs)


# Headings that only wrap a league's grid; any other heading must name a group.
_LEAGUE_HEADINGS = {"results", "results table", "regular season", "league", "season", "first phase", "first stage"}
_NAMED_GROUP = re.compile(r"^[A-Z][\w-]* group$")
_NO_RESULT = {"", "—", "–", "-"}


def grid_label(heading: tuple[str, ...]) -> str | None:
    """`Results` or `Regular season / Results` → `League`; `Championship group / Results` →
    `Championship group`; None for a heading that names neither."""
    parts = [h for h in heading if h.lower() not in _LEAGUE_HEADINGS]
    if not parts:
        return "League"
    return parts[-1] if len(parts) == 1 and _NAMED_GROUP.match(parts[-1]) else None


def _selected(grids: list[tuple[SeasonGrid, WikipediaPin]], sections: list[str] | None) -> list[tuple[SeasonGrid, WikipediaPin]]:
    """The grids a season reads: its only one, or those whose top-level section is one of the seeded
    ones (spec `Grid sections`). Only the top level counts: in 1950-51 the relegation group's grid
    sits under `Relegation group / Results`, which isn't the league's `Results`."""
    if sections is None:
        if len(grids) != 1:
            found = "; ".join(f"{pin.title} (revision {pin.revision}): {' / '.join(g.heading) or 'no heading'}" for g, pin in grids)
            raise WikipediaSourceError(f"{len(grids)} results grids and no `wikipedia_grids` to choose from: {found or 'none'}")
        return grids
    wanted = {s.lower() for s in sections}
    chosen = [(g, pin) for g, pin in grids if g.heading and g.heading[0].lower() in wanted]
    for section in sections:
        if not any(g.heading[0].lower() == section.lower() for g, _ in chosen):
            raise WikipediaSourceError(f"no results grid under the section {section!r}")
    return chosen


async def read_grid_season(src: SeasonSource, store: RevisionStore, seeded: dict[str, str]) -> WikipediaSeason:
    """A league season from the results grids of its pinned revisions (D4): one match per cell, the
    row's club at home. Rows and columns pair by position, and must resolve to the same club."""
    pins = src.wikipedia_source
    assert pins, f"{src.label} has no Wikipedia pins"
    if src.rounds:
        raise WikipediaSourceError(f"{pins[0].title}: `rounds` renames headings above match boxes; a league's grids have none")
    found = [(g, pin) for pin in pins for g in parse_season_grids(await store.html(pin))]
    matches: list[ParsedMatch] = []
    clubs: dict[str, str] = {}
    for grid, pin in _selected(found, src.wikipedia_grids):
        where = f"{pin.title} (revision {pin.revision})"
        label = grid_label(grid.heading)
        if label is None:
            raise WikipediaSourceError(f"{where}: heading {' / '.join(grid.heading)!r} names no league or group")
        qid_of = await store.qids(pin, set(grid.rows) | set(grid.columns))
        sides: list[str] = []
        for title in grid.rows + grid.columns:
            if title not in qid_of:
                raise WikipediaSourceError(f"{where}: club article {title!r} has no Wikidata QID")
        for i, (row, column) in enumerate(zip(grid.rows, grid.columns, strict=True)):
            home, away = seeded.get(qid_of[row], qid_of[row]), seeded.get(qid_of[column], qid_of[column])
            if home != away:
                raise WikipediaSourceError(f"{where}: row {i + 1} is {row!r} ({home}) but column {i + 1} is {column!r} ({away})")
            clubs.setdefault(home, row)
            sides.append(home)
        for cell in grid.cells:
            home, away = sides[cell.row], sides[cell.column]
            line_no = len(matches) + 1
            if cell.score is not None:
                score = ParsedScore(*cell.score, DecidedBy.REGULAR)
                matches.append(ParsedMatch(line_no, label, None, None, None, home, away, score))
            elif cell.text in _NO_RESULT:  # a match without a result, such as one annulled
                matches.append(ParsedMatch(line_no, label, None, None, None, home, away, None, status=MatchStatus.CANCELLED))
            else:
                raise WikipediaSourceError(f"{where}: {clubs[home]} v {clubs[away]} reads {cell.text!r}, not a score")
    return WikipediaSeason(matches, pins[0].title, clubs)


@dataclass(frozen=True)
class WikipediaSeasons:
    """What sync needs to read Wikipedia seasons: the revision store and the seeded QIDs."""

    store: RevisionStore
    seeded: dict[str, str]

    async def read(self, src: SeasonSource, *, grids: bool = False) -> WikipediaSeason:
        """The season from its match boxes, or with `grids` (a league) from its results grids."""
        if grids:
            return await read_grid_season(src, self.store, self.seeded)
        return await read_season(src, self.store, self.seeded)
