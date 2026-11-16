# Design

## Context

- **Sources today:** every stored match comes from openfootball (CC0), read from git clones under `SOURCES_DIR`. Wikipedia is only a verification reference. `ingestion/wikipedia.py` reads rendered articles through the REST API, parses match boxes (`MatchBox`: date, home and away article titles, score, shootout, awarded) and maps article titles to Wikidata QIDs. Its sub-article discovery takes every linked title that extends the season's own.
- **UEFA's terms rule it out.** UEFA.com's terms (section 6.2) forbid automated collection and compiling a database from its content, and its competition regulations claim match data as UEFA's property. We use no UEFA data as a source.
- **The spike, run on 2026-11-16 over 1955-56 to 2010-11:**
  - Each season's boxes parse with a date for every match. The only ones without a result are five walkovers: Linfield v Vorwärts 1961-62, Derry City v Anderlecht 1965-66, Panathinaikos v CSKA Sofia 1972-73, Dynamo Kyiv v Tirana 1982-83 and Dynamo Kyiv v Panathinaikos 1995-96.
  - Five boxes are awarded.
  - There are 4,321 boxes in all. They link 343 distinct clubs, and 189 of them aren't in `seeds/teams.yaml`. Every linked article has a QID.
  - Discovery wrongly pulls in `… European Cup Winners' Cup` articles from 1960-61 to 1991-92, which inflated a first count (1960-61: 51 European Cup boxes plus 16 Winners' Cup boxes, and one more awarded match, Hajduk Split v Marseille). The figures above leave them out. Handball articles add no boxes.

## Goals / Non-Goals

**Goals:**

- Champions League seasons 1955-56 to 2010-11 from Wikipedia: date, stage, teams, score, shootout, awarded.
- Every season says where its data comes from and under which license, and that license follows each match.
- Reproducible syncs: what Wikipedia says today doesn't change the database until someone moves a pin.

**Non-Goals:**

- Scorers, line-ups, venues, attendance and referees from Wikipedia boxes. The boxes have most of them, but the first step is results. Each can follow in its own change, with its coverage flag.
- Other competitions, such as the Cup Winners' Cup, the UEFA Cup and La Liga before 2012-13. Once this change is in, each one is mainly seeds and pins.
- Independent verification of the Wikipedia seasons. RSSSF could serve as a comparison-only reference later.
- Kickoff times. The early boxes rarely give one, so every Wikipedia match is stored date-only, as openfootball matches without a time already are.

## Decisions

### D1. Pins in the season seed

```yaml
- label: 1955-56
  start_year: 1955
  wikipedia_source:
    - {title: "1955–56 European Cup", revision: 1384458360}
- label: 2000-01
  start_year: 2000
  wikipedia_source:
    - {title: "2000–01 UEFA Champions League", revision: 1375976450}
    - {title: "2000–01 UEFA Champions League first group stage", revision: 1372870841}
    - {title: "2000–01 UEFA Champions League second group stage", revision: 1370542174}
    - {title: "2000–01 UEFA Champions League knockout stage", revision: 1360996596}
```

- **Validation:** `wikipedia_source` excludes `file`, `json`, `tz`, `events`, `squads` and `wikipedia`, so a season has exactly one source.
- **The page list is explicit**, so discovery mistakes (D6) can't leak into stored data.
- **Alternative: read the live pages and record the revision.** Rejected. Every sync could change history without anyone reviewing it, and the fingerprint would need the network to tell whether anything changed.
- **Alternative: commit the HTML snapshots to the repo.** Rejected. It adds about 120 large files that the revision ID already identifies. The cache (D2) gives the same reproducibility.

### D2. Fetching and caching revisions

- **Fetch:** REST `page/html/{title}/{revision}`, with the existing polite client (User-Agent, timeouts, one retry).
- **Cache:** the HTML is stored at `SOURCES_DIR/wikipedia/{revision}.html` and read from there afterwards. A revision never changes, so the cache never expires.
- **Fingerprint:** it hashes the pins (titles and revision IDs), not the HTML. An unchanged season is skipped without opening the cache.
- **Failure:** a fetch failure raises the same error a broken source file raises. That season fails and keeps its data, and the others go on (spec `Unattended runs`).

### D3. From boxes to parsed matches

- **One parsed match per box.** A new `ingestion/wikipedia_season.py` turns each box into the `ParsedMatch` sync already stores, so upsert, occurrences, the awarded seed, standings and the fingerprint work unchanged:
  - `round_label`: the heading path, such as `Second group stage / Group A` or `Quarter-finals`;
  - `day`: the box date;
  - `kickoff`: none;
  - `home` and `away`: QID keys (D5);
  - `score`, and `awarded` from the box;
  - `line_no`: the box's position, for error messages.
- **Headings.** Parsoid HTML nests each section in a `<section>` whose first child is the heading, so the box's heading path is the chain of its enclosing section headings below the page title.
  - On a sub-article such as `… knockout stage`, the title suffix is prepended when the headings themselves don't name the stage.
  - `normalize_stage` maps the label, and a label it rejects fails the season (spec `Stage from section headings`).
  - New labels found in the spike that need rules: `Preliminary round`, `First round`, `Second round`, `Eighth-finals`, `Play-off` (as in a replay), `First group stage`, `Second group stage`.
- **Replays.** A replay or deciding play-off in the 1950s and 1960s sits under its tie's heading (for example `Quarter-finals` with a `Replay` box). The `Replay` and `Play-off` sub-headings keep the parent stage, and `occurrence` tells it apart when the pairing repeats in the same order.
- **Two group stages (1999-2000 to 2002-03).** `phase_of` learns `Second group stage` as phase 2, so standings get one table per phase and group, as they already do for the 1974-82 World Cups.
- **Shootouts and extra time** come from the box, which gives the full-time score, and `(a.e.t.)` and `(x–y p)`. `decided_by` follows as it does for openfootball.

### D4. Walkovers and awarded boxes

- **Walkovers:** a box with no result becomes `status=CANCELLED`, with no score, as openfootball's cancelled fixtures already are. A walkover is not a match result, and storing an invented score would misstate the source.
- **Awarded boxes** are already flagged by the parser (`awd.`). They get `seeds/awarded.yaml` entries:
  - Dresden v Red Star 1990-91: abandoned after crowd trouble, so `PARTIAL`.
  - Marseille v Milan 1990-91: Milan left the pitch, so `PARTIAL`.
  - Leeds v Stuttgart 1992-93: Stuttgart fielded too many foreign players and the match was awarded 3–0, so `FULL`.
  - Roma v Dynamo Kyiv 2004-05: abandoned at half-time, so `PARTIAL`.
  - Inter v Milan 2004-05: abandoned in the 73rd minute, so `PARTIAL`.
- **The drafts aren't final.** Each value is confirmed from a source when the seed is written, as in `record-how-awarded-matches-ended`.

### D5. Teams by QID

- **Key:** the reader keys each team as `wikidata:<QID>`, using the client's existing title → QID lookup at the pinned revision's link targets, plus `reference_wikidata` folding as in verification.
- **Resolution:** sync resolves that key through `external_ref(source=wikidata)`, which every seeded team with a QID already has. So `TeamSeed.openfootball` drops its `min_length=1`, and a QID becomes required when a team has no spelling.
- **Unknown QIDs** fail the season with the article title and the QID (spec `Teams resolved by Wikidata QID`), the way unknown spellings do.
- **QID lookups depend on the live site.** Article titles map to QIDs through the live API, and a renamed article still resolves through its redirect. The resolved QIDs are cached next to the HTML (`{revision}.qids.json`), so a cached season stays offline and reproducible.
- **The 189 new teams** are generated by a one-off script (name from the English Wikidata label, `country` from P17 as ISO 3166 or the project's GB-ENG-style code, `kind: CLUB`). They're sorted into `seeds/teams.yaml`, and the PR is reviewed by hand. Clubs whose Wikidata item changed over the years (for example Vorwärts Berlin, linked as `1. FC Frankfurt`) keep a single QID: the one the article links.

### D6. Pinning tool

- **`just wikipedia-pins <article> [<competition> <season>]`** prints a season's pins at the current revisions, ready to paste into the seed. It discovers the sub-articles itself. Given the competition and season, it also lists the box differences from the seeded pins, so a reviewer sees what a pin move changes.
  - **Alternative: edit `competitions.yaml` in place.** Rejected during implementation. Rewriting YAML would drop the seed's comments, and pasting a printed block is just as quick.
- **Discovery fix:** it skips titles whose suffix names another competition (`Cup Winners' Cup`) or another sport (a parenthesised qualifier such as `(handball)`). The same fix goes into verification's discovery, which is harmless for today's seasons.

### D7. Source and license storage

- **`season.source`:** a JSON column, not null, `{publisher, license, pages: [{title, url}]}`.
  - openfootball seasons get `publisher: openfootball` and `license: CC0-1.0`, with the GitHub URL of each file read (`file`, `json`, `events`, squads).
  - Wikipedia seasons link `https://en.wikipedia.org/w/index.php?oldid=<revision>`, which also leads to the page history CC BY-SA attribution needs.
  - The migration backfills every existing season as openfootball with no pages. The code change alters every season's fingerprint, so the next sync fills in the pages.
- **A match's license comes from its season.** Every match query already returns the match's season, which `coverage` needs, so `license` is read from `season.source` without a column on `match`.
  - **Alternative: a `match.license` column.** Rejected during implementation: the proposal assumed match queries had no season, but they all have one, and a copy could drift from its season.
  - **Alternative: a license on the season only.** Rejected. A client paging `/v1/matches` across seasons would have to look up each season to know its terms.
- **Standings** derive from a season's matches, and their response already names the season, so they carry no license field of their own. The README states that derived data follows the season's license.

### D8. Verification and seasons sourced from Wikipedia

- **Skipped:** `verification.py` already skips seasons that name no `wikipedia` article. The seed validation (D1) guarantees that a Wikipedia season names none, so no extra branch is needed.
- **Standings verification** skips them too, for the same reason. Their tables are still computed from the stored matches and served.
- **Group-stage rules from 1991-92** are added under the Champions League `standings` eras, with the points per win and tiebreakers in force each season, cited from UEFA's regulations of the time. Citing a rule isn't reusing UEFA data.
  - Up to 1994-95, a win was worth 2 points.
  - The eras are checked against Wikipedia's group tables while the seeds are written, as a one-off review that isn't stored.

## Risks / Trade-offs

- **Wikipedia errors become our data.** There's no independent check yet (non-goal), and moving a pin is the only way to take a correction. The pinning tool's box diff keeps those moves reviewable. The README says these seasons aren't verified.
- **Share-alike reaches derived data.** Standings and team match lists that include a 1955-2011 season carry CC BY-SA terms for that part. Clients that need CC0 only can filter by `license`. That's why the license is on every match.
- **QIDs drift.** A club article can be merged or retargeted on Wikidata. Pinned revisions keep their link targets, but the title → QID lookup is live, which is why its result is cached with the revision. A new pin re-resolves the QIDs and fails loudly on an unknown one.
- **Size:** the seed grows by 56 seasons with about 120 pins, and the database by 4,321 matches, about 9% more.
