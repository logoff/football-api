# Proposal

## Why

La Liga starts in 2012-13 because openfootball does, but the league has been played since 1929. English Wikipedia (CC BY-SA 4.0, already a season source since `source-older-seasons-from-wikipedia`) has a results grid for every earlier season. Every one of the 81 seasons from 1929 to 2011-12 has a league grid, with 22,305 scores, plus 90 in the 1986-87 second phase. The grids link 60 Wikidata items, 12 of them not seeded yet. One of them, Atlético Aviación, is Atlético Madrid, so there are 59 clubs. A first spike on 2026-11-17 skipped 1929-30, so the counts here are from the implementation. The grids give no date or matchday, though, and neither does Spanish Wikipedia. Today every match must have a kickoff, so these seasons need matches whose date isn't known.

## What Changes

- **Matches without a date.**
  - **BREAKING:** `kickoff_utc` becomes nullable in REST and GraphQL. A null means the source gives no date. Nothing is estimated from the season's dates.
  - Listings sort matches without a date after the dated ones and page through them with the same cursor. Date filters (`from`, `to`) leave them out.
  - Standings count them in full tables. A table `as_of` a date is refused for a season that has matches without one.
  - Catalog rule change: a season can be listed without a date for every match, as long as the source says nothing about dates. A tournament edition whose source dates only some of its matches stays out.
- **Wikipedia results grids as a season source.**
  - A Wikipedia season can be read from the results grids of its pinned revision as well as from match boxes. Each cell gives the home club, the away club and the score.
  - Rows and columns pair up by position and resolve to clubs by QID. One grid in 1946-47 names a club differently in its row and its column.
  - An empty cell becomes a `CANCELLED` match without a score. In 1979-80 the grid leaves Málaga v Salamanca empty: the result was annulled in 1980, then reinstated in 1982.
  - When a page has more than one grid, the seed names the sections to read.
- **La Liga 1929 to 2011-12.**
  - 81 seasons join La Liga with 22,396 matches: 22,395 with a score and the one the grid leaves empty. The Civil War seasons 1936-37 to 1938-39 were never played.
  - The 1986-87 second phase (championship, intermediate and relegation groups) is included, since only La Liga clubs played it.
  - Relegation play-offs and the 1950-51 to 1955-56 relegation groups are left out, since they included Segunda clubs.
  - 11 clubs are added to `seeds/teams.yaml`. The 12th, Atlético Aviación, is folded into Atlético Madrid.
  - Wikipedia's grids carry 28 wrong scores and 3 wrong team links, found by a cross-check with RSSSF. They're stored as they are and listed in `wikipedia-corrections.md`, until someone corrects Wikipedia and the pins move.
- **Era rules for La Liga standings.**
  - 2 points for a win until 1994-95 and 3 from 1995-96. The current era starts in 1992, which is wrong but didn't matter while the seasons began in 2012.
  - Tie-breakers per era, checked against Wikipedia's final tables once, without storing anything.
  - Point deductions and awarded matches the season notes describe, curated in `seeds/standings.yaml` and `seeds/awarded.yaml`. A grid can't mark an awarded match, so for these seasons the awarded seed also sets the flag.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `matches`: A match's kickoff can be unknown. That changes how listings order and filter matches.
- `ingestion`: Wikipedia seasons can be read from results grids. That covers sections, pairing by position, empty cells and the awarded flag from the seed.
- `standings`: Tables include matches without a date. A table as of a date is refused for seasons that have them.
- `catalog`: La Liga seasons from 1929. A season whose source gives no dates at all can be listed.

## Impact

- **Database:** `match.kickoff_utc` becomes nullable, through an Alembic migration with no backfill.
- **Code:**
  - `ParsedMatch.day` becomes optional.
  - Sync, fingerprint and occurrence handling for matches without a date.
  - The results-grid parser, which needs headings and pairing by position, and the Wikipedia season reader.
  - Keyset pagination over a nullable column.
  - Sorting in `standings.py`, and the `as_of` check in `season_tables.py`.
  - REST schemas, GraphQL types and `schema.graphql`.
- **API:** `kickoff_utc` and `kickoffUtc` can be null. That breaks clients that assume a value.
- **Seeds:**
  - 81 La Liga seasons with pins in `competitions.yaml`.
  - 12 teams.
  - The La Liga standings eras.
  - Point deductions and awarded entries.
- **Docs:** the README coverage row, a note on matches without dates, and the `openspec/config.yaml` context.
- **Load on Wikipedia:** 81 page revisions, fetched once and then cached.
