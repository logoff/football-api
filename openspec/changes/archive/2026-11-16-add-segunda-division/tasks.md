# Tasks

## 1. Seeds

- [x] 1.1 Add Segunda División (Q35615) to `seeds/competitions.yaml` after La Liga, with La Liga's standings rules and the 13 seasons 2012-13 to 2024-25 (design D1). Verify that each file parses to 462 matches.
- [x] 1.2 Add the 8 new clubs to `seeds/teams.yaml` (design D3). Verify that a local sync raises no unknown-team or ambiguous-name error, and that the Wikidata check passes for every new QID.

## 2. Docs

- [x] 2.1 Update the README coverage table and the `openspec/config.yaml` scope context. Verify that mdformat leaves no changes.

## 3. Integration

- [x] 3.1 Run `just sync-competition Q35615 --verify` locally. Verify 13 seasons of 462 matches, 2018-19's 21 awarded matches, and 2024-25's 9 `SOURCE_BEHIND`. Review every `MISMATCH` by D4 and record the outcome in the PR.
- [x] 3.2 Check standings for a few seasons against the final tables on Wikipedia, including 2018-19 (Reus expelled).
- [x] 3.3 Verify that `just typecheck`, `just test` and `openspec validate add-segunda-division --strict` all pass.

## Workflow follow-up

- Open the PR without describing any deployment.
- Open the upstream PR to openfootball/espana for 2024-25's missing results.
- Archive this change once it's merged.
