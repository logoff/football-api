# Tasks

## 1. Model and sync

- [x] 1.1 Add the `played` enum (`FULL`, `PARTIAL`, `NONE`) and a nullable `match.played` column with an Alembic migration (design D4). Verify that `just migrate` upgrades and downgrades cleanly.
- [x] 1.2 Load `seeds/awarded.yaml` with match and team entries, validated as in design D2. Verify with seed loader tests: unknown competition, season or QID, a duplicate match, and a match entry that repeats a team entry.
- [x] 1.3 Set `played` in sync: `FULL` for a `COMPLETED` match that isn't awarded, otherwise the match entry, then the team entry, and else null with a warning (design D3). Add the season's seed entries to the season fingerprint. Verify with sync tests for each case, and that editing an entry re-syncs an otherwise unchanged season.

## 2. Curation

- [x] 2.1 For each of the 21 awarded matches outside Segunda División, find an official source (league, federation or UEFA/CONMEBOL) for whether it was played in full, in part or not at all, and add the entry. Where none exists, cite the best source and say so in a comment. Verify that each draft value in proposal.md was confirmed or corrected.
- [x] 2.2 Once #47 is merged, add the Reus team entry from 19 January 2019. Verify 21 `NONE` and 21 `FULL` after a sync.

## 3. API

- [x] 3.1 Expose `played` in the REST match schema and the GraphQL `Match` type, and regenerate `schema.graphql` with `just graphql-schema`. Verify with API and GraphQL tests for an awarded `FULL`, a plain `FULL` and a null case. `PARTIAL` and `NONE` are covered by the sync tests (1.3), since the fixture data has no such match.

## 4. Docs

- [x] 4.1 Update the README's paragraph on awarded matches and the `openspec/config.yaml` data-depth context. Verify that mdformat leaves no changes.

## 5. Integration

- [x] 5.1 Run a full local sync. Verify that no awarded match is left with `played: null` and that no warning is logged. Outcome: 49,281 completed matches. The 21 awarded ones are 10 `FULL`, 5 `PARTIAL` and 6 `NONE`, with no warning. Reus's 21 wait for 2.2.
- [x] 5.2 Verify that `just typecheck`, `just test` and `openspec validate record-how-awarded-matches-ended --strict` all pass.

## Workflow follow-up

- Open the PR without describing any deployment.
- Archive this change once it's merged.
