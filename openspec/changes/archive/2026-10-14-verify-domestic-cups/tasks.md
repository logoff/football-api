# Tasks

## 1. Match-box reader

- [x] 1.1 Write hand-made HTML fixtures (no Wikipedia text) for both templates, covering: plain, `a.e.t.`, `p`, `agg.`, `awd.`/`Awarded`, `w/o`/`Walkover`/`Void`/`Bye`/`v`, footnotes, and a box without a date. Verify that the fixtures load in tests.
- [x] 1.2 Implement `parse_match_boxes` (D1) and `WikipediaClient.match_boxes`. Verify with unit tests for each score form and both templates.
- [x] 1.3 Add a `network`-marked smoke test that reads `2024–25 DFB-Pokal` and finds 63 boxes with scores. Verify with `just test -m network`.

## 2. Verification

- [x] 2.1 Implement cup pairing (D2) and comparison with shootouts (D3), and dispatch by format (D4). Verify with tests: a unique pairing, a re-replay paired by date, two legs, a shootout match and a shootout mismatch, a no-result box (`UNCONFIRMED`), an awarded box, an unpaired stored match counted in the summary, and a league season still using the grid.

## 3. Seeds and docs

- [x] 3.1 Add `wikipedia` titles to the 32 cup seasons. Verify that every title resolves (a script run in the PR).
- [x] 3.2 Update the README (cups are now verified, and the `--verify` example with the cup QIDs). Verify that mdformat leaves no changes.

## 4. Integration

- [x] 4.1 Run a full local sync and a verified run of the six cups on an empty database. Record per-cup status counts and unpaired counts, and review every `MISMATCH` (source error, Wikipedia error, or reader bug) in the PR.
- [x] 4.2 Verify that `just typecheck`, `just test` and `openspec validate verify-domestic-cups --strict` all pass.

## Workflow follow-up

- Open the PR without describing any deployment.
- Archive this change once it's merged.
