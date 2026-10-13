# Tasks

## 1. Seeds

- [x] 1.1 Add the eight seasons 1992-93 to 1999-00 to the Premier League in `seeds/competitions.yaml` (D1). Verify with a script, run in the PR, that each file parses to 462 or 380 matches, all with scores.
- [x] 1.2 Add the 21 aliases and the Wimbledon F.C. team (D2) to `seeds/teams.yaml`. Verify that the seed loader accepts the file and a local sync raises no unknown-team error.

## 2. Docs

- [x] 2.1 Update the README coverage table (Premier League 1992-93 to 2026-27, 35 seasons, and date-only kickoffs before 2000-01 except 1998-99) and the `openspec/config.yaml` scope context. Verify that mdformat leaves no changes.

## 3. Integration

- [x] 3.1 Sync and verify the Premier League locally on an empty database. Verify 35 seasons and the per-season match counts, and review every `MISMATCH` (source error, Wikipedia error, or parser bug). Record the outcome in the PR.
- [x] 3.2 Verify that `just typecheck`, `just test` and `openspec validate extend-premier-league-history --strict` all pass.

## Workflow follow-up

- Archive `add-domestic-cups` before this change, since both modify the Season catalog requirement.
- Archive this change once it's merged.
