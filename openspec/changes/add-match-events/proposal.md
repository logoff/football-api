# Add Match Events

## Why

v0.1 (`init-football-api-v0.1`) stops at final scores and goal scorers. Lineups, substitutions and cards are the next layer clients expect from a football API, and one in-scope source already publishes them completely: `openfootball/club-worldcup/more/2025_clubworldcup-full.txt` carries lineups, substitutions, cards, captain, referee and attendance for all 63 matches of the FIFA Club World Cup 2025. Starting there proves the event model on real, complete data before widening to other competitions.

**Depends on:** `init-football-api-v0.1` (match, player, squad, and goal model; reconciliation rules; API conventions).

## What Changes

- Ingest, for **FIFA Club World Cup 2025 only**:
  - **Lineups** — starting XI and substitutes who came on, with captain flag and the source's line grouping (`GK - DEF - MID - FWD`), from which a formation string (e.g. `4-3-3`) is derived.
  - **Substitutions** — minute, player off, player on, side; including chained substitutions (`(14' ZIZO (79' MOHAMED AFSHA))`).
  - **Cards** — `YELLOW`, `SECOND_YELLOW`, `RED`, with minute and player.
  - **Referee name** and **attendance** on the match.
- Expose them on the existing match resource via `GET /v1/matches/{id}?expand=lineups,substitutions,cards`, plus `referee` and `attendance` fields on the match.
- Add `coverage.events` to every match: `full` for Club World Cup 2025, `none` elsewhere.
- Event minutes carry added time separately (`90+5'` → minute 90, added 5).

## Capabilities

### New Capabilities

- `match-events`: lineups, substitutions, cards, referee and attendance for a match — how they are ingested, identified, and exposed through the match resource, and how per-match event coverage is reported.

### Modified Capabilities

None. `matches` is introduced by `init-football-api-v0.1`, which is not yet archived; this change only adds fields and expand values alongside it and does not alter its requirements.

## Impact

- **Schema:** new tables `lineup_entry`, `substitution`, `card`; new nullable columns `match.referee_name`, `match.attendance`. Additive Alembic migration.
- **Ingestion:** new parser for the `-full` file's lineup/event block; reuses v0.1 squad resolution and name normalisation.
- **API:** new `expand` values and fields on `/v1/matches/{id}` and `/v1/matches`; no breaking changes.
- **Out of scope:** events for any other competition (WC 2022 / Euro `-full` files not yet verified), xG, shots, pitch positions, referees as an entity, per-event external IDs.
