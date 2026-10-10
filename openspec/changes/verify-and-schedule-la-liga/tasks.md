# Tasks

## 1. Seeds: several seasons per competition

- [x] 1.1 Change `CompetitionSeed.season` to `seasons: list[SeasonSource]` (at least 1, labels unique per competition) and add the optional `wikipedia` article title to `SeasonSource`. Verify with seed tests for an empty list, a duplicate label, and a valid multi-season seed.
- [x] 1.2 Convert all 13 entries in `seeds/competitions.yaml` and the fixture seeds in `tests/fixtures/seeds` to `seasons:` without changing their content. Verify that `just test` passes unchanged apart from the seed format.
- [x] 1.3 Make `sync.py` and `ingestion/sources.py` loop over every season of a competition. Verify with a sync test that a two-season fixture competition gets two seasons and matches in both.

## 2. La Liga 2012-13 to 2026-27

- [x] 2.1 Add fixture excerpts for the older text layouts (2012-13 style `Home v Away score`; 2020-21 style `Home score Away` with unindented dates) and make the parser handle them. Verify with parser tests that check teams, scores, half-time and kickoff for each layout.
- [x] 2.2 List the 15 La Liga seasons in `seeds/competitions.yaml` (`file`, `json`, `tz`, `wikipedia`). Verify that each season's text file parses to exactly the `# Matches` count in its header, with a script run listed in the PR.
- [x] 2.3 Add every missing La Liga club with QID and per-year aliases to `seeds/teams.yaml`, drafted with `tools/propose_teams.py`. Verify that a local full `just sync` raises no unknown-team error and the Wikidata check passes.
- [x] 2.4 Update the README coverage table and `openspec/config.yaml` context (La Liga 2012-13 to 2026-27). Verify that mdformat leaves no changes.

## 3. Competition-scoped, unattended sync

- [x] 3.1 Add `argparse` options `--competition QID` (repeatable), `--verify` and `--no-refresh`. An unknown QID exits non-zero before any write. Verify with CLI tests.
- [x] 3.2 Collect per-season failures instead of aborting: the other seasons commit and the exit code is 1. Verify with a test where one fixture season has a broken file.
- [x] 3.3 Exit 3 with a clear message when the schema isn't at Alembic head. Verify with a test against a database at an older revision.
- [x] 3.4 Add a `pg_try_advisory_lock` held for the run; a second run exits 4 without writing. Verify with a test holding the lock from another connection.
- [x] 3.5 Log one summary line per competition-season. Add a `just sync-competition QID *flags` recipe and document the CLI in the README, including the exit codes. Verify that the recipe runs locally for La Liga.

## 4. Wikipedia results-grid reader

- [x] 4.1 Add BeautifulSoup and write hand-made HTML fixtures (no Wikipedia text) covering: header and row links, the `—` diagonal, empty and `a` cells, `<sup>` notes, and a non-grid table to ignore. Verify that the fixtures load in tests.
- [x] 4.2 Implement grid detection and cell parsing into `(home_title, away_title, score | None)`. Verify with unit tests, including "no grid" and "two tables, one grid".
- [x] 4.3 Implement a batched title-to-QID lookup (`pageprops`, `redirects=1`, ≤50 titles per call) and the REST HTML fetch: project User-Agent, 20 s timeout, one retry on 429/5xx honouring `Retry-After` up to 30 s, `wikipedia_enabled` and endpoint settings. Verify with tests using an `httpx` mock transport, including a 429 then 200 and a timeout.
- [x] 4.4 Add one live smoke test marked `network`, excluded by default, that reads `2024–25 La Liga` and finds 380 scores. Verify that it passes with `just test -m network`.

## 5. Verification statuses

- [x] 5.1 Add an Alembic revision with the `match_verification` table (uuidv7 `id`, `match_id` FK cascade, `reference` and `status` enums, `checked_at`, unique `(match_id, reference)`) and the model. Verify that upgrade and downgrade both run on a fresh database.
- [x] 5.2 Implement verification of a season: pair cells with `(season, LEAGUE, home, away)` through Wikidata QIDs, compute the status, upsert, and delete rows that no longer apply. Verify with tests for each of the four statuses, a status change on a re-run, an unknown team that is skipped with a warning, and a season without a grid that keeps its statuses.
- [x] 5.3 Log the disagreement lines (MISMATCH, SOURCE_BEHIND) and the per-season status counts. Make sure no reference value is written to the database. Verify with tests on the log output and on the table columns.
- [x] 5.4 Wire up `--verify`: run only for synced seasons whose seed has `wikipedia`; skip silently otherwise; exit 0 despite mismatches or the reference being unavailable. Verify with CLI tests for La Liga and for the Premier League.

## 6. API

- [x] 6.1 Add `verification` (`null` or `{status, reference, checked_at}`) to the match schemas and responses. Verify with API tests for a verified match and an unverified competition.
- [x] 6.2 Add the `?verification=` filter on `/v1/matches`; an invalid value returns 422 with the error envelope. Verify with API tests, and check that OpenAPI shows the enum.

## 7. Container image

- [x] 7.1 Install `git` and `ca-certificates` in the runtime stage and set `HOME=/tmp`. Verify that `docker run --rm -e SOURCES_DIR=/tmp/src -e DATABASE_URL=… <image> python -m football_api.sync --competition Q324867 --verify` completes against the compose database, and that the default CMD still serves the API.

## 8. Integration

- [x] 8.1 Full local run on an empty database: `just sync`, then `just sync-competition Q324867 --verify`. Verify that La Liga has 15 seasons of 380 matches each, the verification counts are logged, and every MISMATCH is reviewed (each one is a source error, or a parser bug that gets fixed). Record the outcome in the PR.
- [x] 8.2 `just typecheck` and `just test` pass, and the `openspec validate verify-and-schedule-la-liga` passes.

## Workflow follow-up

- Archive `init-football-api-v0.1` before this change, so the `catalog` and `ingestion` deltas have main specs to apply to.
- Open the implementation as a PR that doesn't describe any deployment. The schedule and its writable `SOURCES_DIR` volume are set up outside this repo, after the new image is published.
- Archive this change once it's merged and deployed.
