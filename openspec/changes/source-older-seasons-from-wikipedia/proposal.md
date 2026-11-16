# Proposal

## Why

openfootball (CC0) is our only data source, and its history is short: the Champions League starts in 2011-12, La Liga in 2012-13 and Serie A in 2013-14. The official archives that go further back don't allow reuse. UEFA.com's terms (section 6.2) forbid scraping its content and compiling a database from it, and they count data as content. UEFA's competition regulations also claim match data and databases as its exclusive property. English Wikipedia is openly licensed (CC BY-SA 4.0), and we already read it to verify about 5,900 matches. A spike over all 56 European Cup and Champions League seasons from 1955-56 to 2010-11 parsed every one of the 4,321 matches with a date, and every one with a score apart from 5 walkovers.

## What Changes

- **Each season names its source and license.**
  - Every season carries a `source` with the publisher, the license (`CC0-1.0` or `CC-BY-SA-4.0`) and the pages it was read from. It's served on the season in REST and GraphQL.
  - Every match carries the license of its season, so a client paging matches across seasons knows which terms apply to each row.
  - The README gives the attribution the CC BY-SA seasons require, and says that data from those seasons is served under CC BY-SA 4.0.
  - This only adds fields, so nothing breaks.
- **Wikipedia can be a season's source.**
  - A season seeded with `wikipedia_source` lists its article and sub-articles, each pinned to a revision ID. Sync reads the match boxes of exactly those revisions, never the live pages.
  - A Wikipedia edit changes nothing until someone moves a pin, so sync stays reproducible, and the season fingerprint covers the pins.
  - Revisions are cached under `SOURCES_DIR` because they never change. A season whose pins haven't moved needs no network.
- **Stage from the section heading.**
  - Each match box takes its stage from the heading it sits under: `Preliminary round`, `First round`, `Group B`, `Quarter-finals`, `Final`…
  - A heading that doesn't map to a stage fails the season instead of guessing.
- **Teams by Wikidata QID.**
  - Wikipedia boxes link club articles, so a team resolves through the article's QID, as verification already does. A team seed no longer needs an openfootball spelling.
  - 189 clubs that played the European Cup are added to `seeds/teams.yaml` with their QIDs.
- **European Cup 1955-56 to 1991-92 and Champions League 1992-93 to 2010-11** join the existing Champions League competition as 56 earlier seasons with 4,321 matches. They cover the competition proper; qualifying rounds stay out, as they do from 2011-12. That includes the group-stage standings rules from 1991-92.
- **Verification skips seasons sourced from Wikipedia.** Comparing a season with its own source proves nothing, so those matches get no verification status. Seasons sourced from openfootball are verified exactly as today.
- **Walkovers and awarded matches.**
  - A box with no result (`w/o`, a withdrawal) is stored `CANCELLED` without a score.
  - The 5 awarded ones are flagged and need entries in `seeds/awarded.yaml`: Dresden v Red Star and Marseille v Milan 1990-91, Leeds v Stuttgart 1992-93, and Roma v Dynamo Kyiv and Inter v Milan 2004-05.

## Capabilities

### New Capabilities

- `season-sources`: Which source and license each season comes from, how that's served with seasons and matches, and the attribution the README gives.

### Modified Capabilities

- `ingestion`: Wikipedia revisions as a season source next to openfootball, with stages from section headings, teams by QID, walkovers and a fingerprint that covers the pins.
- `catalog`: Champions League seasons from 1955-56, and team seeds that don't need an openfootball spelling.
- `match-verification`: A season sourced from Wikipedia isn't verified. The rule that reference content is never stored applies to verification, not to a season's own source.

## Impact

- **Database:** a `source` JSON column on `season`, with an Alembic migration that backfills openfootball and `CC0-1.0`. A match's license is read from its season.
- **Code:**
  - `ingestion/wikipedia.py`: fetching pinned revisions, an on-disk cache, and headings for each match box.
  - A new Wikipedia season reader that turns match boxes into the parsed matches sync already stores.
  - Seed models, sync, `season_check`, REST schemas, GraphQL types and `schema.graphql`.
- **Seeds:** 56 seasons with pins in `competitions.yaml`, 189 teams, the group-stage rules from 1991-92, and 5 awarded entries.
- **Tooling:** a `just` recipe that prints a season's pins at the current revisions and lists the box changes from the seeded ones.
- **Docs:** README sources, coverage and license sections, and the `openspec/config.yaml` context.
- **Load on Wikipedia:** about 120 page revisions, fetched once and then cached.
