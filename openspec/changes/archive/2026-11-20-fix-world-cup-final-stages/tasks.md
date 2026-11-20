# Tasks

## 1. Code

- [x] 1.1 Add `bronze` to the third-place stage rule. Verify with a `normalize_stage` test that `Bronze final` is `THIRD_PLACE` and `Final` is still `FINAL`.
- [x] 1.2 Rename the seed field `wikipedia_rounds` to `rounds`, valid for every season, and leave it out of the fingerprint while unset. Make a season read from results grids reject it. Verify with seed loader tests.
- [x] 1.3 Apply `rounds` to openfootball seasons in the sync's read path, on each `/` part of a round label, and fail on a listed heading no match has. Verify with sync tests for the spec scenarios `openfootball final round that is a group` and `Heading that isn't there`.

## 2. Seeds and docs

- [x] 2.1 Rename `wikipedia_rounds` to `rounds` on the 31 Copa América seasons, and add `rounds: {Final Round: Second group stage}` to the 1950 World Cup.
- [x] 2.2 Sync every competition, and compare every stored stage before and after. Verify that only 1950's six final-round matches and the 2026 third-place match change. Check that the 1950 final-round table matches Wikipedia's when verified. Outcome: of 88,509 stored matches, exactly those seven changed stage, and each kept its id. The sync logged no warnings. With `--verify`, all 17 rows of the 1950 tables are `VERIFIED`, including the four of the final round.
- [x] 2.3 Update the README where it names `FINAL` labels or the seed fields. Verify that mdformat leaves no changes.

## 3. Checks

- [x] 3.1 Verify that `just typecheck`, `just test` and `openspec validate fix-world-cup-final-stages --strict` all pass. Outcome: 460 tests pass.

## Workflow follow-up

- Implement in the same PR as this proposal.
- Archive this change once the PR is merged.
