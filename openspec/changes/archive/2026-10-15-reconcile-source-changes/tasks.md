# Tasks

## 1. Sync

- [x] 1.1 Reuse an unmatched match of the same season, teams and date (±1 day) when the exact key misses, updating its stage, occurrence and openfootball reference (D1). Verify with a sync test that relabels a round and keeps the UUIDs.
- [x] 1.2 Delete the season's matches the sync didn't see, with their external references (D2), and log the count. Verify with a sync test that removes a match: the match, its goals and its verification row are gone, and the other UUIDs are unchanged.

## 2. Integration

- [x] 2.1 On a database synced from the current cup files, apply the europe#13 relabel and re-sync. Verify that Coupe de France 2024-25 still has 200 matches, 16 of them now `R32`, with unchanged UUIDs.
- [x] 2.2 Verify that `just typecheck`, `just test` and `openspec validate reconcile-source-changes --strict` all pass.

## Workflow follow-up

- Archive this change once it's merged.
