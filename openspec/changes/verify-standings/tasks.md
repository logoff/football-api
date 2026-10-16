# Tasks

## 1. Table builder

- [x] 1.1 Move the endpoint's table building into `season_tables` (D1). Verify that the existing standings API tests pass unchanged.

## 2. Reader

- [x] 2.1 Wikipedia standings-table parser and client method with sub-articles and de-duplication (D2). Verify with tests on hand-made HTML: header mapping, flags and notes, an extra column, a non-standings table ignored, and the same table in two articles.

## 3. Verification

- [x] 3.1 `standing_verification` model and migration (D4). Verify that `alembic upgrade head` runs on a fresh database.
- [x] 3.2 Compare and record (D3), called from `--verify`. Verify with tests using a fake reference: a verified table, a points mismatch, an unpaired table, and a provisional table that keeps no status.
- [x] 3.3 `verification` on standings rows in the API. Verify with an API test.

## 4. Integration

- [x] 4.1 README: standings verification. Verify that mdformat leaves no changes.
- [x] 4.2 Run a full verified run locally. Review every `MISMATCH` against an official source, and fix the cause: a rule, a missing deduction or order, a source error upstream, or a Wikipedia error. Record each outcome in the PR.
- [x] 4.3 Verify that `just typecheck`, `just test` and `openspec validate verify-standings --strict` all pass.

## Workflow follow-up

- Add any accepted mismatches to the nightly job's `known-mismatches.txt` (infra).
- Archive this change once it's merged.
