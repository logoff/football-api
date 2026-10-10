# Design

## Context

- **One season per competition.** Seeds hold exactly one season each (`season:` in `seeds/competitions.yaml`). La Liga points at `espana/2024-25/1-liga.txt`. openfootball's `espana` repo has `1-liga.txt` for every season from **2012-13 to 2026-27**, 15 in all; nothing older exists in openfootball. The `football.json` mirror has `es.1.json` for the same 15. The 2026-27 file is updated weekly by an automated job and has scores but no scorers.

- **The text files' layout varies by year.** 2012-13 to 2016-17 use `HH:MM  Home  v Away  score (ht)` under dated headings. 2020-21 uses `HH:MM  Home  score (ht)  Away`, with date lines unindented. The v0.1 parser was only exercised on 2024-25.

- **How the sync runs today.** `python -m football_api.sync` syncs every competition. It aborts the whole run on the first `SyncError`, and it has no CLI options. It uses one transaction per competition-season, which is kept.

- **The image can't sync.** The runtime image has no `git`, so `ensure_sources` can't clone. The API container runs `alembic upgrade head` before starting.

- **What Wikipedia looks like.** La Liga results grids appear in at least three layouts:

  - inline in the article (`{{#invoke:sports results}}`, e.g. 2010–11, 1995–96);
  - transcluded from `Template:<season> La Liga table` with `show_matches=only` (2026–27);
  - kept in the table template while the article only shows standings (2025–26's template has no `match_` cells at all).

  The **rendered HTML** is the same in all of them: a `wikitable plainrowheaders` table with N team abbreviations across the top, each linking to the club article, and N rows, each headed by a club link. Cells are `2–1` (en dash), `—` on the diagonal, and empty or `a` (a linked placeholder) for unplayed matches. This was checked on 1995–96, 2025–26 and 2026–27.

- **What's already known.** Teams are identified by Wikidata QID (`external_ref`, source `wikidata`). Wikipedia article titles resolve to QIDs through the Action API (`prop=pageprops&ppprop=wikibase_item`).

## Goals / Non-Goals

**Goals:**

- A verification module that knows nothing about La Liga specifically: any season whose seed names a Wikipedia article can be verified.
- Verification is safe to run on a schedule: idempotent, network failures are tolerated, and the effect of a run is visible only through statuses and logs.

**Non-Goals:**

- Verifying scorers, kickoff times, venues or anything other than the final score.
- Verifying knockout competitions, whose grids don't exist.
- Doing anything with a disagreement except reporting it, such as voting between sources or overriding data.
- The schedule itself: frequency, scheduler and manifests live outside this repo.

## Decisions

### D1. Parse rendered HTML, not wikitext

Fetch `GET /api/rest_v1/page/html/{title}` and find the grid in the HTML. Identifying the grid:

- it's a table with a header row of N short labels, each linking to an article;
- it has N body rows, each headed by an article link;
- N ≥ 2, and at least one cell matches `^\d+–\d+`.

Footnote markers (`<sup>`) are removed before reading a cell.

- *Alternative: wikitext.* Rejected because it would need three or more layouts, template expansion and Lua-module parameters (`team_order` vs `team1…`, several cells per line). The rendered output is the module's own contract and stays uniform.
- *Alternative: `action=expandtemplates`.* It still returns wikitext and has the same parsing problem.

### D2. The seed names the reference article

Each season seed gets an optional `wikipedia` field holding the article title, e.g. `wikipedia: "2025–26 La Liga"`. A season is verifiable if and only if the field is set.

- *Alternative: derive the title from the label.* Rejected: titles use en dashes, season formats vary, and pages get renamed. A field that's set explicitly fails loudly; a derived title fails quietly.

### D3. Identity through Wikidata only

- **Collect the teams.** Gather the grid's row and column link targets and resolve them in one batched Action API call (`titles=` takes up to 50, `redirects=1`) to `wikibase_item`.
- **Map them to stored teams.** Map QID to team through `external_ref(entity_type=team, source=wikidata)`.
- **Pair the cells.** Row is home, column is away. Each cell pairs with the stored match `(season, stage=LEAGUE, home, away)`. That key is unique because a league season is a double round-robin.
- **Unknown teams.** A team whose QID doesn't resolve is skipped with a warning, per the spec.

No fuzzy name matching, consistent with how v0.1 identifies teams.

### D4. Storage: one row per match and reference

New table `match_verification`:

| Column       | Type                                                        |
| ------------ | ----------------------------------------------------------- |
| `id`         | uuidv7                                                      |
| `match_id`   | FK, on delete cascade                                       |
| `reference`  | enum `WIKIPEDIA`                                            |
| `status`     | enum `VERIFIED`, `MISMATCH`, `UNCONFIRMED`, `SOURCE_BEHIND` |
| `checked_at` | timestamptz                                                 |

`(match_id, reference)` is unique. Rows are upserted by that key. If neither source has a score any more, the row is deleted. The reference's score is **never** a column (spec: reference content is never stored); it appears only in the log.

- *Alternative: columns on `match`.* Rejected because a second reference (e.g. football-data.co.uk) would need more columns. A separate table also keeps `match` free of anything a reference wrote.

The API shows the row for `WIKIPEDIA` as `verification`, or `null` if there isn't one. The filter `?verification=` is a semi-join on that row.

### D5. CLI and exit codes

Use `argparse` in `football_api.sync`:

- `--competition QID`: repeatable.
- `--verify`.
- `--no-refresh`: skip git fetch; for tests and offline runs. This exposes the existing `refresh_sources` parameter.

The run proceeds in this order:

1. Resolve and validate the QIDs.
1. Check the schema is at Alembic head. If not, exit 3 with "run migrations first".
1. Take the advisory lock `pg_try_advisory_lock(<fixed key>)` on a dedicated connection held for the whole run. If it isn't granted, exit 4 with "sync already in progress".
1. Sync each requested season in its own transaction, collecting failures instead of aborting.
1. Verify the seasons that synced successfully and have a reference.
1. Exit 1 if any season failed, otherwise 0.

Exit codes, as implemented: 1 a season or the seed step failed, 2 usage error (unknown QID; argparse already uses 2), 3 schema not migrated, 4 lock busy. Distinct exit codes let a scheduler's logs tell the cases apart. Any non-zero code still marks the job failed.

- **Why check the schema instead of migrating.** Migrations belong to the API container (its CMD). If a scheduled job ran them too, two migrators could race after an image update.
- **Why an advisory lock instead of row locks.** The scheduler may overlap runs, and so may a manual `just sync` during a scheduled one. Advisory locks are released automatically if the process dies.

### D6. Polite Wikipedia access

- **What it uses:** `httpx` (already a dependency), with timeouts of 20 s per request.
- **Identification:** `User-Agent: football-api/<version> (+https://github.com/logoff/football-api)`. No personal contact.
- **Volume:** per season, one REST call plus one Action API call. La Liga's 15 seasons are about 30 requests per run.
- **Retries:** one, on 429 and 5xx, honouring `Retry-After` up to 30 s. After that the season is skipped, per the spec.
- **Settings:** `wikipedia_enabled` and the endpoints, mirroring the existing Wikidata settings.

### D7. Seeds: `season` becomes `seasons`

`CompetitionSeed.seasons: list[SeasonSource]`, with at least one entry and labels unique within a competition. All 13 entries in `competitions.yaml` are converted in place, which is mechanical. La Liga lists all 15 seasons, 2012-13 to 2026-27, each with:

- `file: espana/<label>/1-liga.txt`;

- `json: football.json/<label>/es.1.json`, which the existing currency rule uses only when it is at least as complete as the text. Mid-season it usually isn't, so 2026-27 falls back to text automatically;

- `wikipedia: "<YYYY>–<YY> La Liga"`, with an en dash;

- `tz: Europe/Madrid`.

- **Why not `1-liga-full.txt` for 2025-26.** It's a different format variant, and adopting it, which would add scorers, is its own change.

- **Clubs.** Every club in any of the 15 seasons that isn't seeded yet is added to `seeds/teams.yaml` with a QID and the aliases each year's file uses, e.g. `RC Celta`, `RC Celta de Vigo` and `Celta Vigo`. Expect roughly 15–20 clubs, such as Córdoba, Eibar, Huesca, Sporting Gijón, Real Zaragoza, Málaga, Deportivo and Racing Santander. `tools/propose_teams.py` drafts them, and the existing Wikidata check verifies them. The authoritative list is the sync's unknown-team errors.

- **Parser coverage.** Every season file must parse to its declared match count (380). The layout variants above get fixture excerpts and tests; any parser gap found is fixed in this change.

- *Alternative: accept both `season` and `seasons`.* Rejected because two spellings of one thing would last forever, and all the seeds belong to this repo.

### D8. Image can sync

The runtime stage installs `git` and `ca-certificates` (`--no-install-recommends`, apt lists removed), adding about 30 MB. It also ships `seeds/`: the seeds directory becomes a `SEEDS_DIR` setting, relative to the working directory like `SOURCES_DIR` and `alembic.ini`, because the old path was computed from the source tree and doesn't exist in an installed package. The default command is unchanged. A scheduler runs `python -m football_api.sync …` with `SOURCES_DIR` on a writable volume. `HOME` is set to `/tmp` so `git` can run as `nobody`.

- *Alternative: download GitHub tarballs over HTTPS instead of git.* Rejected because it changes `ensure_sources` for every user and loses incremental fetches. That can be revisited if image size matters.

### D9. Tests without network

- **Grid parser:** synthetic HTML fixtures reproducing the structure in Context (header links, row links, `—`, empty and `a` cells, `<sup>` notes, a non-grid table that must be ignored). They are written by hand, not copied from Wikipedia, so no CC BY-SA text enters the repo.
- **Title-to-QID resolution:** injected as a function, and faked in tests.
- **Live smoke test:** one test against Wikipedia, marked `network` and excluded by default.

## Risks / Trade-offs

- **[Wikipedia changes the module's HTML]** → Grid detection relies only on structural traits (square, links, score cells). A season with no grid found logs a warning and keeps its statuses, and the summary shows zero checks, which makes the break visible.
- **\[A vandalised Wikipedia cell creates a false `MISMATCH`\]** → Statuses never change data, and the next run re-evaluates. This is the price of an open reference, and the log makes it easy to inspect.
- **[openfootball lags]** The 2026-27 file was last updated on 2026-09-21 while Wikipedia already shows later results. → That's what `SOURCE_BEHIND` surfaces. Freshness is bounded by openfootball's update cadence, and that is now measurable.
- **[Older layouts hide parser gaps]** → Each season's match count is checked against the file header (`# Matches 380`). Cross-checking with Wikipedia also catches wrong scores and swapped home/away teams across all 15 seasons.
- **[New season each summer]** The seeds must gain `2027-28` with its file and article, plus any promoted clubs. → It's a deliberate, reviewed seed edit. The sync's unknown-team error is the checklist.
- **[Breaking seed format]** → Only this repo reads the seeds. Fixture seeds in `tests/fixtures/seeds` are converted in the same change.

## Migration Plan

1. One Alembic revision adds the `match_verification` table and its two enums. The downgrade drops them, and nothing else depends on them.
1. When the new image deploys, the API container migrates on start. Until then, scheduled syncs exit 3 ("run migrations first") without writing.
1. **Rollback:** go back to the previous image. The extra table is ignored by older code. The downgrade is only needed to remove it.
1. **Ordering:** `init-football-api-v0.1` is archived before this change, so that the `catalog` and `ingestion` deltas have main specs to apply to.
