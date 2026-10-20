# Tasks

## 1. Implementation

- [x] 1.1 Scoped spellings, seed checks, and year-aware resolution for matches, events and squads (D1). Verify with seed tests (overlap, plain-and-scoped, valid load) and a sync test.
- [x] 1.2 Removed spellings dropped (D2), and squad players following their listing (D3). Verify with the sync test: matches and players keep their UUIDs, and the old team keeps only its scoped key.
- [x] 1.3 `reference_wikidata` in verification (D4). Verify with a seed test (another team's item is refused).

## 2. Integration

- [x] 2.1 On a database synced with the old seeds, sync the World Cup and Euro, then verify 1938, 1998 and 2000. Verify that the 8 matches and the squad move, nothing is unpaired, and a second sync changes nothing.
- [x] 2.2 Verify that `just typecheck`, `just test` and `openspec validate historic-team-identities --strict` all pass.

## Workflow follow-up

- Archive this change once it's merged.
