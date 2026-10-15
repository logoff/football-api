# Proposal

## Why

The sync only ever inserts or updates matches. When openfootball relabels a round or removes a match, the old rows stay. openfootball/europe#13, now merged, renames the Coupe de France 2024-25 round `10. Runde` to `Round of 32`, which changes those 16 matches' stage from `ROUND` to `R32`. Today the next sync would add 16 new matches and keep the 16 old ones, so the round would appear twice.

## What Changes

- **Relabelled matches keep their identity.** A source match with no row under its key (season, stage, home, away, occurrence) reuses a match of the same season, teams and date (within a day) that the current sync hasn't matched yet. Its stage, occurrence and source reference are updated, and its UUID, status and history are kept.
- **Removed matches are deleted.** After a season syncs, its matches that the source no longer lists are deleted, with their goals, verification status and external references. The deletion is logged per season.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ingestion`: Idempotency. The match key includes `occurrence`, relabelled matches are reused, and matches gone from the source are removed.

## Impact

- **Code:** `sync.py`, in the match lookup and at the end of each season.
- **Database:** no schema change.
- **Data:** the next cup sync applies europe#13 in place: the 16 matches keep their UUIDs and move to `R32`.
