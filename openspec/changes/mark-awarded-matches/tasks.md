# Tasks

## 1. Parsing and storage

- [x] 1.1 Add `awarded` to `ParsedMatch`, set from the `[awarded]` tag in the text parser and from `"status": "awarded"` in the JSON reader, and compare it in `is_current` (D3). Verify with parser and JSON tests.
- [x] 1.2 Add `Match.awarded` and its Alembic revision, and set it in `sync_match`. Verify with a sync test (tagged and untagged lines), upgrade/downgrade/upgrade on a synced database, and `alembic check`.
- [x] 1.3 Expose `awarded` in `MatchOut`. Verify with an API test and the OpenAPI schema.

## 2. Verification

- [x] 2.1 Skip awarded matches with a level stored score in `apply_grid`, deleting any existing status (D2). Verify with tests: a level awarded match against a 0–3 cell gets no status and no disagreement line, a previously `MISMATCH` row is removed, and a decisive awarded match is `VERIFIED`.

## 3. Docs and integration

- [x] 3.1 Document `awarded` in the README (coverage notes and verification). Verify that mdformat leaves no changes.
- [x] 3.2 Run a local full sync and a verified run of the five leagues on an empty database. Verify that the 14 tagged matches have `awarded` true, that Bastia v Lyon has no status, and that there's no `MISMATCH` left.
- [x] 3.3 Verify that `just typecheck`, `just test` and `openspec validate mark-awarded-matches --strict` all pass.

## Workflow follow-up

- Archive this change once it's merged.
