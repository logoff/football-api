# Proposal

## Why

The nightly sync re-processes all 227 seasons and re-reads about 850 Wikipedia pages, although almost nothing changes from one night to the next. The last two runs took 21 and 28 minutes: about 7 of sync and the rest verification. Only the 20 or so seasons in progress get new results, and Wikipedia edits about 5 of the 225 season articles a day. The run grows with every season we add, and option 2 (verifying line-ups and cards) will read more pages.

## What Changes

- **Unchanged seasons aren't re-synced.** Each season keeps a fingerprint of everything its sync reads: its source files, its seed entry, `seeds/teams.yaml` and the code. A season whose fingerprint matches its last successful sync is skipped. An upstream correction, a seed change or a deploy changes the fingerprint, so nothing is missed.
- **Unchanged seasons aren't re-verified.** Verification records the revision ID of every Wikipedia page it reads for a season. Before verifying, one batched query returns the current revision IDs (50 pages per request). A season is re-verified only when it was re-synced, when any of its pages has a new revision, or when it is among the seventh of seasons checked longest ago. That rotation re-checks every season at least about once a week, which catches the changes a revision ID can't show: edits to a template the article includes.
- **Skipped seasons still report.** They log their stored statuses in the same summary and disagreement lines, marked as unchanged, so the nightly Kuma report and the GitHub summary keep counting every season and keep flagging an unreviewed mismatch every night.
- **`--full`** ignores the stored fingerprints and re-syncs and re-verifies everything, as today.
- **The GitHub full sync and verification runs weekly instead of nightly**, plus on merge to `main` and by hand. It starts from an empty database, so it always does a full run.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ingestion`: new requirements Unchanged seasons are skipped, and Forced full sync (`--full`).
- `match-verification`: new requirements Unchanged seasons are not re-verified, Verification rotation, and Incomplete verification keeps its state. Modified: Reference content is never stored or served (page titles and revision IDs are stored), and Disagreement report (unchanged seasons report their stored statuses).

## Impact

- **Code:** `sync.py` (fingerprints, skip, `--full`), `verification.py` (skip and report stored statuses), `ingestion/wikipedia.py` (record revision IDs, batched revision query).
- **Database:** one new table, `season_check`, internal and not exposed in the API. Migration required.
- **API:** no change. A skipped season's `verification.checked_at` keeps the time it was last actually compared.
- **CI:** `verify.yml` schedule from daily to weekly.
- **Nightly job:** expected to take about 5 to 8 minutes instead of 21 to 28, except the first night after a deploy, which is a full run. The job's comment ("Full history every night") needs a follow-up infra PR; its arguments don't change.
