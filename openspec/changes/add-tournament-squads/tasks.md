# Tasks

## 1. Seeds and parsing

- [x] 1.1 Name the squad file of every tournament season that has one (D1), and add `Türkiye` to Turkey. Verify that a local sync of the World Cup, Club World Cup, Euro and Copa América succeeds.
- [x] 1.2 Optional shirt number in `more` squads (D2). Verify with a unit test, and that the 1930–1950 squads parse (250 to 326 players each).
- [x] 1.3 Spacing-insensitive matching (D3). Verify with a unit test: a unique match resolves, and an ambiguous one doesn't.

## 2. Docs and integration

- [x] 2.1 README: squads coverage and player links. Verify that mdformat leaves no changes.
- [x] 2.2 Measure locally the share of line-ups, substitutions, cards and goals linked to players, before and after, and record it in the PR.
- [x] 2.3 Verify that `just typecheck`, `just test` and `openspec validate add-tournament-squads --strict` all pass.

## Workflow follow-up

- Archive this change once it's merged.
