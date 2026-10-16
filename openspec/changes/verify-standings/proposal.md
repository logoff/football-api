# Proposal

## Why

Standings are computed from the stored results with ranking rules and deductions curated by hand. Two kinds of error can't be seen from the results alone:

- **A missing deduction.** Ligue 1's are the least complete.
- **A tie-breaker encoded wrongly**, or an era boundary off by a season.

Wikipedia publishes the final table of every season and group. Comparing against it, as match verification already does for scores, turns those silent errors into flagged rows.

## What Changes

- **Final tables are compared with Wikipedia's.** The verifier reads the standings tables of the season article and its group sub-articles, and pairs each with one of our final tables when both hold the same teams (by Wikidata QID).

- **Each row gets a status:**

  - `VERIFIED` when position, played, won, drawn, lost, goals for and against, and points all agree;
  - `MISMATCH` otherwise, with both values logged;
  - `UNCONFIRMED` when no Wikipedia table holds the table's teams.

  In-progress tables aren't compared.

- **The API shows the status:** each standings row gets a `verification` object, as matches have.

- **It runs with `--verify`**, after match verification, for the seasons synced. The nightly job and its Kuma report pick it up unchanged, since mismatches are logged in the same form.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `standings`: rows carry a verification status against Wikipedia's final table.

## Impact

- **Code:** the Wikipedia client (a standings-table reader), the verifier, the standings API, and a shared table-building function used by both.
- **Database:** a new `standing_verification` table.
- **Network:** the same articles match verification already fetches. Pages are cached within a run.
