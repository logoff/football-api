# Tasks

## 1. Copa Sudamericana

- [ ] 1.1 Add `final stages` to the wrapper headings (D2). Verify with a reader test for the spec scenario `Round under the final stages`. Sync every Wikipedia season before and after, and check that no stored stage changes.
- [ ] 1.2 Add the competition (Q60585) and its 13 openfootball seasons, 2012 to 2024, with `wikipedia` references (D1). Draft the missing clubs with `tools/propose_teams.py`, review them, and add them to `teams.yaml` (D4). Verify that every season syncs, and that the 2016 final's legs are `CANCELLED`.
- [ ] 1.3 Pin 2025 with `rounds: {First stage: Preliminary round}` (D1). Verify 157 matches with stages `PRELIMINARY`, `GROUP` (eight groups), `PLAYOFF`, `R16`, `QF`, `SF` and one `FINAL`.
- [ ] 1.4 Add the standings eras, cited (D5). Verify with the openfootball seasons' standings verification, and compare 2025's group tables with Wikipedia's once. Record the result in the PR.
- [ ] 1.5 Update the README (coverage row, sources, deferred note) and the OpenSpec context. Run `just typecheck`, `just test` and a full sync, and verify that mdformat leaves no changes.

## 2. Africa Cup of Nations

- [ ] 2.1 Add the competition (Q83145) and the 30 missing national teams by QID (D3, D4).
- [ ] 2.2 Pin the 35 editions from 1957 to 2025. Use `rounds` for 1959 and 1976, settle 1963's `… Final` sub-article and 2002's duplicate final while pinning, and check each box count against the article (D3). Verify that `FINAL` holds only finals and their replays, and that the 1957 and 2010 matches without a score are `CANCELLED`.
- [ ] 2.3 Add the standings eras, cited (D5). Compare every computed group table with Wikipedia's once, without storing anything, and record the result in the PR.
- [ ] 2.4 Update the README and the OpenSpec context. Run a full sync from an empty Wikipedia cache, then a second one that skips every season. Verify that `just typecheck`, `just test` and `openspec validate afcon-and-copa-sudamericana --strict` pass.

## Workflow follow-up

- Implement in two PRs: the Copa Sudamericana (1), then the Africa Cup of Nations (2).
- Open the PRs without describing any deployment.
- Archive this change once the last PR is merged.
