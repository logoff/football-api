# Tasks

## 1. Storage

- [ ] 1.1 Add the `season_check` model and its Alembic migration (D3). Verify that the migration applies and downgrades on an empty database, and that deleting a season deletes its row.

## 2. Sync

- [ ] 2.1 Compute the code fingerprint from the installed package's `.py` files (D2). Verify with a test that it's stable across calls and changes when a file changes.
- [ ] 2.2 Compute the season fingerprint, taking the file list from the same functions that read the files (D1). Verify with tests that each input changing on its own changes it: the text file, the JSON mirror, the events file, a squad file, the season's seed entry, the competition's seed entry, `seeds/teams.yaml` and the code fingerprint.
- [ ] 2.3 Skip a season whose fingerprint matches, log it as unchanged with its match count, and store the fingerprint after each successful sync in the same transaction. Add `--full`. Verify with sync tests: a repeat sync re-syncs nothing; a changed file re-syncs only its season; a failed season is retried; `--full` re-syncs everything.

## 3. Verification

- [ ] 3.1 Record `content-revision-id` with every page the Wikipedia client fetches, and add a batched current-revision query (`prop=info`, `redirects=1`, 50 titles per request) (D4). Verify with client tests on recorded responses, including a redirect and a missing page.
- [ ] 3.2 Decide which seasons to verify (D5), and store the titles, revisions, fingerprint and time after each complete verification. Verify with tests for each rule: synced in this run, no stored verification, a changed article, a changed sub-article, a redirected or missing page, the rotation over seven runs, and an unavailable reference leaving the state as it was.
- [ ] 3.3 Log skipped seasons' stored statuses (D6). Verify with tests that the lines match the report patterns in `tools/verify_report.py`, and that a stored mismatch is logged on every run.

## 4. CI and docs

- [ ] 4.1 Move `verify.yml`'s schedule to weekly (D7).
- [ ] 4.2 Document `--full`, skipping and the meaning of `checked_at` in the README.

## 5. Integration

- [ ] 5.1 On an empty database, run a full sync with `--verify`, then a second run. Verify that the second run re-syncs nothing, verifies only the rotation's seasons, reports the same totals and the same mismatch, and record both timings.
- [ ] 5.2 Change one season's source file and one season's article revision (by editing the stored revision), and run again. Verify that exactly those seasons are re-synced or re-verified.
- [ ] 5.3 Verify that `just typecheck`, `just test` and `openspec validate skip-unchanged-seasons --strict` all pass.

## Workflow follow-up

- Infra PR: update the nightly job's comment ("Full history every night").
- Archive this change once it's merged.
