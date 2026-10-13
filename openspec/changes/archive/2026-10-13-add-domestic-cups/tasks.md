# Tasks

## 1. Competition format

- [x] 1.1 Add the `CompetitionFormat` enum, the `Competition.format` column, the seed field (required) and the competition upsert. Set `format` on all 13 existing seed entries and the test fixture seeds. Verify with a seed test (missing or unknown format rejected) and a sync test that writes it.
- [x] 1.2 Expose `format` in `CompetitionOut` and add the `?format=` filter on `/v1/competitions`. Verify with API tests for the filter, an invalid value (422), and the enum in OpenAPI.

## 2. Stages and occurrences

- [x] 2.1 Add `PRELIMINARY` and `ROUND` to `Stage`, and the rules for `Round N`, `N. Round`, `N. Runde` and `Preliminary round` after the named-round rules (D2). Verify with `normalize_stage` cases, including `Round of 16` still mapping to `R16`.
- [x] 2.2 Add `Match.occurrence` and the new unique key. In `sync_season`, number repeated pairings by D3. Verify with sync tests for both cases: a fixture where a scored pairing reappears gives two matches, and a postponed-then-relisted pairing gives one match with `original_kickoff_utc`. Also verify that a re-sync keeps both UUIDs.
- [x] 2.3 Expose `occurrence` in the match schema, and document the `matchday`/round number in OpenAPI. Verify with an API test.
- [x] 2.4 Write one Alembic revision for 1.1 and 2.1 to 2.2 (D1 to D3, including the downgrade). Verify that upgrade, downgrade and upgrade run on a database with synced data, and that `alembic check` reports no drift.

## 3. Seeds

- [x] 3.1 List the six cups' seasons in `seeds/competitions.yaml` (D5). Verify with a script, run in the PR, that each file parses and every round label maps to a stage.
- [x] 3.2 Check each cup's `tz` against a few known kickoffs. Record the checks in design.md under "Source coverage". Verify that the stored UTC kickoffs match.
- [x] 3.3 Draft and review the missing team spellings (D4). Verify that the seed loader accepts the file, that `just sync` raises no unknown-team error, and that the clubs seeded without a QID are listed in the PR.

## 4. Docs

- [x] 4.1 Update the README: the coverage table with the cups and a format column, the deferred super cups and league cups, and the new `stage` values called out for clients. Update the `openspec/config.yaml` scope context. Verify that mdformat leaves no changes.

## 5. Integration

- [x] 5.1 Full local run on an empty database (`just sync`). Verify the per-cup season and match counts against the files, that FA Cup 2023-24 has both Scarborough v Forest Green games, that a second sync is idempotent, and that the leagues' match counts are unchanged.
- [x] 5.2 Verify that `just typecheck`, `just test` and `openspec validate add-domestic-cups --strict` all pass.

## Workflow follow-up

- Open the PR without describing any deployment. Whether the scheduled sync includes cups is decided outside this repo.
- Follow-up change: verify cups (and other knockout competitions) against Wikipedia's per-match boxes.
- Archive this change once it's merged.
