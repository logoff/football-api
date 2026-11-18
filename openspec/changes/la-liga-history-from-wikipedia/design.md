# Design

## Context

- **Wikipedia seasons today:** `wikipedia_season.read_season` reads the match boxes of a season's pinned revisions and turns each one into the `ParsedMatch` sync already stores. Revisions and their QIDs are cached under `SOURCES_DIR/wikipedia/` (change `source-older-seasons-from-wikipedia`).
- **Results grids:** `wikipedia.parse_results_grid` already reads league grids, for verification only. It takes the first grid on the page, pairs rows with columns by article title and keeps no heading.
- **Every match has a date today:**
  - `ParsedMatch.day` and `match.kickoff_utc` are both required.
  - `/v1/matches` pages with a keyset on `(kickoff_utc, id)`, ascending.
  - Sync sets `season.starts_on` and `ends_on` from the earliest and latest match day.
  - `standings.py` sorts matches by kickoff, both to drop a group's repeated pairings and to order connected components.
  - `season_tables.py` filters on kickoff for `as_of`.
- **The spike, run on 2026-11-17 over the 80 English Wikipedia articles from `1929 La Liga` to `2011–12 La Liga`.** It skipped `1929–30 La Liga`, which has a grid like the others, so the implementation has 81 seasons and 22,396 matches:
  - Every article has a grid, and every cell has a score apart from Málaga v Salamanca 1979-80, which was annulled. That gives 22,215 scores in the league grids, and 90 more in the 1986-87 second phase. Counting the annulled match, that makes 22,306 matches.
  - No grid gives a date or a matchday. The only dated boxes are relegation play-offs.
  - The grids link 60 clubs, and 12 of them aren't seeded: Atlético Aviación, CD Málaga, UE Lleida, Atlético Tetuán, CD Condal, Burgos CF (1936–1983), UD Salamanca, AD Almería, CD Logroñés, Real Burgos, CP Mérida and CF Extremadura.
  - In 1946-47, two rows link an older article name (`Atlético Bilbao`, `Real Gijón`) while their columns link the current one, so pairing by title creates 2 phantom matches.
  - 1950-51 to 1955-56 add a `Relegation group` grid that includes Segunda clubs.
  - 1986-87 has four grids: `Regular season`, `Championship group`, `Intermediate group` and `Relegation group`.
  - 67 cells from 1997-98 onwards link match articles (El Clásico and the like). No cell carries a footnote or an awarded mark.

## Goals / Non-Goals

**Goals:**

- League results for La Liga 1929 to 2011-12, including the 1986-87 second phase. Each match has its home club, its away club and its score, and no date.
- A dateless match is a first-class value through the database, sync, REST, GraphQL and standings, with no invented dates.
- Final tables that agree with Wikipedia's, under per-era rules and curated adjustments.

**Non-Goals:**

- **Dates or matchdays from another source.** The user chose to store matches without dates. A dated open source can fill them in later through `original_kickoff_utc`-style updates without changing match identity, since identity doesn't involve the date.
- **Historical club names.** A team is served under its seeded name, so Atlético Aviación's 1939-1946 seasons show `Atlético Madrid`. Names by period need their own change.
- **Carrying first-phase points into 1986-87's second phase.** Each group table counts only its own matches, so its order can differ from the official 1986-87 ranking. The README says so.
- **Relegation play-offs and the 1950s relegation groups.** Segunda clubs played in them.
- **Verifying these seasons.** Comparing a season with its own source proves nothing, as for the Champions League seasons. The one-off table comparison in D7 checks the ranking rules, not the results.

## Decisions

### D1. A null kickoff

- **`match.kickoff_utc` becomes nullable**, and `ParsedMatch.day` becomes `date | None`. The Alembic migration only drops `NOT NULL`, so the downgrade fails while any match has no date. That's documented in the migration.
- **No other field changes:**
  - `matchday` stays null.
  - `original_kickoff_utc` is set only when a known date changes.
  - `season.starts_on` and `ends_on` are null when no match has a day, and they span only the dated matches otherwise.
  - Season status still comes from match statuses.
- **Alternative: a placeholder date**, such as the season's 1 September, plus an `estimated` flag. Rejected. It's invented data. Clients that ignore the flag would sort, filter and chart it as real.
- **Alternative: a separate `date_known` boolean next to a non-null kickoff.** Rejected for the same reason, plus two fields that can contradict each other.

### D2. Listing and paging dateless matches

- **Sort key:** `/v1/matches` and the GraphQL connection sort on `(coalesce(kickoff_utc, '9999-12-31 23:59:59+00'), id)`, so dateless matches come last and keep a total order by `id`. `id` is a UUIDv7 inserted in grid order.
- **Cursors:** a cursor encodes the sentinel for a dateless row. A sentinel was picked over Postgres's `infinity` because it is an ordinary `datetime` on the Python side, so cursors and drivers need no special case. No real kickoff comes near it.
- **Index:** an expression index on the sort key keeps the listing indexed. The plain index on `kickoff_utc` stays for date filters.
- **Date filters:** `from` and `to` compare `kickoff_utc`, so they leave nulls out with no extra code.
- **Alternative: `NULLS LAST` with a cursor branch for nulls.** Rejected. A row tuple that contains a null doesn't compare in Postgres, so the keyset would need two predicates. With a sentinel it stays one tuple comparison.

### D3. Standings without dates

- **Sorting:** both kickoff sorts in `standings.py` use `(kickoff is None, kickoff)`. A league table doesn't depend on that order. The group play-off rule only runs when a pairing is met once, which never happens in a double round robin.
- **`as_of`:** on a season with any dateless match it returns 422 (spec `Standings endpoint`). Counting the matches would claim knowledge we don't have, and leaving them out would show a table of zeros.
- **`TableMatch.kickoff_utc`** becomes optional.

### D4. Results grids in the reader

- **Parser:** `parse_season_grids(html)` returns every grid with its heading path, using the section walk `_heading` already gives boxes. Each cell keeps its row and column index.
  - `parse_results_grid`, used by verification, stays as it is: the first grid, paired by title. Its output for today's verified seasons doesn't change.
- **Which pages are read:** a Wikipedia season of a `LEAGUE` competition reads grids, and the others read boxes. The competition's format already says which shape the season has. A league page's boxes are play-offs, which are out of scope.
- **Sections:** a new optional season field, `wikipedia_grids: [<section>, …]`. It's only valid with `wikipedia_source` on a `LEAGUE` competition (spec `Grid sections`). Without it, a page must have exactly one grid. A grid matches a seeded section by its top-level heading only. In 1950-51 the relegation group's grid sits under `Relegation group / Results`, so the league's `Results` mustn't select it.
- **Pairing by position:**
  - Row *i* and column *i* must resolve to the same QID, or the season fails.
  - Cell (*i*, *j*) with *i* ≠ *j* is row *i*'s club at home against column *j*'s club away.
  - QIDs come from `RevisionStore.qids` over both row and column titles, as for boxes.
- **Labels and stages:**
  - A grid under `Results`, `Results table` or `Regular season` gets round label `League`, stage `LEAGUE`. The spike found `Results table` on 16 pages.
  - A grid under `<Name> group` gets `<Name> group`, stage `GROUP` and group name `<Name>`. `normalize_stage` and `group_of` learn that form, anchored at the end of the label so `First group stage` is unaffected.
  - Any other section fails the season, as an unknown box heading does.
- **Cells:** a score gives `COMPLETED`, `REGULAR`. A league match has no extra time. An empty cell gives `CANCELLED` without a score, like a walkover box. `line_no` is the cell's position, row-major, for error messages.
- **Fingerprint:** it covers `wikipedia_grids` along with the pins.

### D5. Awarded matches from the seed

- **The problem:** a grid has no awarded mark, so the source can't set the flag.
- **The rule:** for a season read from grids, sync marks `awarded` on every pairing listed in `seeds/awarded.yaml` for that season, and takes `played` from the entry as usual.
  - An entry that matches no pairing fails the season.
  - An entry that matches a match already marked awarded by an openfootball source stays a no-op, as today.
- **Finding candidates:** each season's notes are searched for `awarded`, `walkover`, `did not show`, `annulled` and `forfeit`. Every hit is confirmed from a source, as in `record-how-awarded-matches-ended`. The spike found Málaga v Almería 1979-80, which Málaga didn't turn up for.
- **Alternative: a new `awarded:` list in `competitions.yaml`.** Rejected. `awarded.yaml` already holds the facts about an awarded match, with its reason and source.

### D6. Teams

- **11 of the 12 unseeded clubs** are added from Wikidata, with name, country and `kind: CLUB`, and reviewed by hand, as in `source-older-seasons-from-wikipedia` D5.
- **Atlético Aviación** (Q16549751) goes under `reference_wikidata` of Atlético Madrid (Q8701): it's the same club, renamed in 1947.
- **Burgos CF (1936–1983) and Real Burgos** stay separate teams from today's Burgos CF (Q852079), since Wikidata treats them as different clubs. So does CD Málaga from Málaga CF.

### D7. Ranking rules and adjustments

- **Points:**
  - The La Liga eras become 2-1-0 from 1929 and 3-1-0 from 1995. The current era starts in 1992, which is wrong for 1992-93 to 1994-95.
  - The 1995 era adds `h2h_reapply` to today's tie-breakers. That only changes 1995-96, where it puts Oviedo above Athletic Club as Wikipedia does. No table from 2012-13 changes.
- **Tie-breakers before 1995:** no regulation text of the time was found. Wikipedia's tables settle every tie with `h2h_points, h2h_reapply, h2h_goal_difference, goal_difference, goals_for`: head-to-head points among the clubs level, then again among those still level, before head-to-head goal difference. The multi-club ties of 1963-64, 1969-70, 1972-73 and 1981-82 need that order. No goal-ratio era was needed.
- **Curated entries:** Málaga −3 in 1979-80 for forfeiting against Almería, whose 0–1 is flagged awarded and `NONE`, and Racing −1 in 2003-04. Deductions have no `effective` date, since there are no dates to place them against.
- **Check:** every computed final table was compared with Wikipedia's once, using `parse_standings`, and nothing was stored. 54 of 84 tables agree. The other 30:
  - **Scores wrong in Wikipedia's grid.** These are 16 seasons with 28 cells, including 1979-80's empty Málaga v Salamanca, which was a 0–3. Every grid cell was cross-checked with RSSSF's crosstables and round lists, read only to compare. Of the 28 corrections, 24 also make the grid agree with the page's own table. The other 4 rest on RSSSF plus a match report or a recorded decision.
  - **Team links wrong in Wikipedia's grid:** 1964-65, where Las Palmas's row links CD Málaga, and 1988-89 and 1989-90, which link Málaga CF, founded in 1994, instead of CD Málaga.
  - **Wikipedia's tables wrong while the grid matches RSSSF:** 1929, 1930-31, 1967-68, 1968-69, 1971-72, 1973-74, 1980-81 and 2000-01. 1961-62 has both kinds.
  - **1986-87's three group tables:** Wikipedia's carry the first-phase points over, which is a non-goal.
- **What's stored:** the user chose to keep the grids as Wikipedia has them, rather than leave those seasons out, and to correct Wikipedia later. `wikipedia-corrections.md` lists every cell and link, with what it should be and the evidence. Once Wikipedia is corrected, moving those pins takes the fix, and the pinning tool shows the cell diff.

### D8. Delivery

Three PRs: dateless matches (D1–D3), grid reading (D4, D5), then the seasons, teams, rules and docs (D6, D7).

## Risks / Trade-offs

- **Breaking change for clients** → `kickoff_utc` can now be null. A strict client that parses it as a non-null datetime breaks the first time it reads a pre-2012-13 La Liga match. The README and the OpenAPI schema say so. The project has no external clients that need a deprecation window.
- **Wikipedia errors become our data** → as for the Champions League, and here they are known: 28 scores and 3 team links (D7). The README lists them. Only moving a pin takes a correction, and the pinning tool now diffs grid cells as well.
- **Share-alike** → every La Liga team's history from 1929 to 2011-12 is CC BY-SA. Clients that need CC0 only can filter by `license`, which is on every match already.
- **1986-87 group tables differ from the official ranking** → that's a documented non-goal. The `final` status of the championship group could mislead, and the README calls it out.
- **Size** → +22,396 matches, about 45% more than today. Sync time grows a little: one cached HTML per season, and no per-match network calls.

## Migration Plan

- **Deploy order:** the migration ships with the first PR. Existing data is untouched, since every stored match keeps its kickoff.
- **Rollback:** the downgrade works until the first dateless season is synced. After that, the rollback is to delete those seasons and then downgrade.
