"""Pin a season to the current revisions of its Wikipedia pages, and show what moving the pins
changes (source-older-seasons-from-wikipedia, design D6): box by box, or for a league cell by cell
(la-liga-history-from-wikipedia).

    just wikipedia-pins "1960–61 European Cup"
    just wikipedia-pins "1960–61 European Cup" Q18756 1960-61   # also diff against the seeded pins

It prints the `wikipedia_source:` block to paste into seeds/competitions.yaml; it never edits the seed.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence

from football_api.infra.settings import get_settings
from football_api.ingestion.openfootball.text_parser import ParsedMatch
from football_api.domain.enums import CompetitionFormat
from football_api.ingestion.seeds import SeasonSource, WikipediaPin, load_competitions
from football_api.ingestion.wikipedia import WikipediaClient
from football_api.ingestion.wikipedia_season import RevisionStore, WikipediaSeason, read_grid_season, read_season

Row = tuple[str, str, str, str, str]  # stage label, date, home, away, result


def pins_yaml(pins: Sequence[WikipediaPin]) -> str:
    lines = ["wikipedia_source:"]
    lines += [f'  - {{title: "{p.title}", revision: {p.revision}}}' for p in pins]
    return "\n".join(lines)


def _result(m: ParsedMatch) -> str:
    if m.score is None:
        return "no result"
    return f"{m.score.home}–{m.score.away} {m.score.decided_by.value}" + (" awarded" if m.awarded else "")


def rows(read: WikipediaSeason) -> set[Row]:
    return {
        (m.round_label, m.day.isoformat() if m.day else "no date", read.clubs.get(m.home, m.home), read.clubs.get(m.away, m.away), _result(m))
        for m in read.matches
    }


def box_diff(old: set[Row], new: set[Row]) -> list[str]:
    """`- ` for rows only the old pins have, `+ ` for rows only the new ones have, in match order."""
    changed = [("-", r) for r in old - new] + [("+", r) for r in new - old]
    return [f"{sign} {' | '.join(r)}" for sign, r in sorted(changed, key=lambda c: (c[1][1], c[1][2], c[0] == "+"))]


def seeded_season(qid: str, label: str) -> tuple[SeasonSource, bool] | None:
    """The seeded season, and whether it's read from results grids (a league)."""
    comp = next((c for c in load_competitions() if c.wikidata == qid), None)
    src = next((s for s in comp.seasons if s.label == label), None) if comp else None
    return (src, comp.format is CompetitionFormat.LEAGUE) if comp and src else None


async def read(src: SeasonSource, store: RevisionStore, *, grids: bool) -> WikipediaSeason:
    return await (read_grid_season if grids else read_season)(src, store, {})


async def run(title: str, qid: str | None, label: str | None) -> int:
    settings = get_settings()
    async with WikipediaClient(rest=settings.wikipedia_rest, api=settings.wikipedia_api) as wiki:
        titles = await wiki.season_titles(title)
        revisions = await wiki.revisions(titles)
        pins = [WikipediaPin(title=t, revision=revisions[t]) for t in titles if t in revisions]
        print(pins_yaml(pins))
        if qid is None or label is None:
            return 0
        seeded = seeded_season(qid, label)
        if seeded is None or not seeded[0].wikipedia_source:
            print(f"\n# {qid} {label} has no seeded pins to compare with", file=sys.stderr)
            return 0
        old, grids = seeded
        store = RevisionStore(settings.sources_dir / "wikipedia", wiki)
        new = old.model_copy(update={"wikipedia_source": pins})
        diff = box_diff(rows(await read(old, store, grids=grids)), rows(await read(new, store, grids=grids)))
        print(f"\n# {len(diff)} {'grid cell' if grids else 'box'} change(s) from the seeded pins", file=sys.stderr)
        for line in diff:
            print(f"# {line}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m football_api.wikipedia_pins", description="Pin a season to the current revisions of its Wikipedia pages.")
    parser.add_argument("title", help="the season article, e.g. `1960–61 European Cup`")
    parser.add_argument("competition", nargs="?", help="competition QID, to diff against the seeded pins")
    parser.add_argument("season", nargs="?", help="season label, to diff against the seeded pins")
    args = parser.parse_args(argv)
    sys.exit(asyncio.run(run(args.title, args.competition, args.season)))


if __name__ == "__main__":
    main()
