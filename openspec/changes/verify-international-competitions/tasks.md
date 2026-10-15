# Tasks

## 1. Reader

- [x] 1.1 Add sub-article discovery (D1) and box de-duplication (D2) to the Wikipedia client's box reading. Verify with tests using hand-made HTML fixtures: links to group, knockout, qualifying-stage and separate qualification sub-articles; a women's edition; a redirect duplicate; a box repeated in the main and sub-article.
- [x] 1.2 Dispatch `TOURNAMENT` to the box reader (D3). Verify with a verification test for a tournament season, and check that the cup and league tests still pass.

## 2. Seeds

- [x] 2.1 Add `wikipedia` titles for the 101 international editions (D4). Verify that every title resolves (a script run in the PR).

## 3. Docs

- [x] 3.1 README: the international competitions are verified. Update the coverage table's Verified column and the verification paragraph. Verify that mdformat leaves no changes.

## 4. Integration

- [x] 4.1 Run a full local sync, then a verified run of the eight competitions, on an empty database. Record per-competition status counts, the number of unpaired matches and the request count. Review every `MISMATCH` against a third source (source error, Wikipedia error, or reader bug) and record the outcome in the PR.
- [x] 4.2 Verify that `just typecheck`, `just test` and `openspec validate verify-international-competitions --strict` all pass.

## Workflow follow-up

- Archive this change once it's merged.
