# Tasks

## 1. Sync

- [x] 1.1 Release moved spellings (D1) and replace corrected QIDs (D3). Verify with sync tests: a spelling moved to its own club, and a corrected QID.
- [x] 1.2 Matches follow their listing (D2), and team seasons follow the source (D4). Verified by the moved-spelling test (match count of the new team, seasons of the old one).

## 2. Seeds

- [x] 2.1 Move the five spellings, add the three clubs and correct the four QIDs. Verify that each QID matches the club's English Wikipedia article.

## 3. Integration

- [x] 3.1 On a database synced from the old seeds, sync with the new ones. Verify that it succeeds, that each moved club has its matches, and that a second sync changes nothing.
- [x] 3.2 Verify that `just typecheck`, `just test` and `openspec validate correct-team-identities --strict` all pass.

## Workflow follow-up

- Archive this change once it's merged.
