# Add Match Events — Design

## Context

Builds directly on `init-football-api-v0.1`: its `match`, `player`, squad (`player_team_season`) and `goal` tables, the reconciliation rules in its design (squad-first players, case- and accent-insensitive name matching, capitalised-surname title-casing, ordinal-keyed child rows), and its API conventions (UUID paths, `?expand=`). See `proposal.md` for motivation; behaviour is specified in `specs/match-events/spec.md`.

The only source is `club-worldcup/more/2025_clubworldcup-full.txt`. Verified on 2026-10-10: 63 matches, each with both lineups, a `Refs:` line and `Att:` on the header; 228 `[Y]`, 11 `[R]`, 5 `[Y/R]` tags; 126 `[c]` tags (one per side). The v0.1 sync already reads this file for goals and kickoff offsets.

Source shape:

```
Sun Jul 13 15:00 UTC-4 @ Giants Stadium, New York/New Jersey (East Rutherford), Att: 81118
  Chelsea FC (ENG) v Paris Saint-Germain (FRA)  3-0
     (Cole PALMER 22', 30', JOAO PEDRO 43')

Chelsea FC: Robert SANCHEZ - Marc CUCURELLA, Levi COLWILL [Y 81'], Trevoh CHALOBAH,
      Reece JAMES [c] (77' Kiernan DEWSBURY-HALL), Malo GUSTO [Y 40'] - Enzo FERNANDEZ (61' ANDREY SANTOS),
      ...
Refs: Alireza FAGHANI (AUS)
```

## Goals / Non-Goals

**Goals:**

- One parser for the lineup block that yields lineup entries, substitutions and cards from a single pass.
- Same identity and idempotency model as v0.1 goals, so sync stays byte-for-byte stable.

**Non-Goals:**

- A general event timeline table (`match_event` with a `type` column). Three narrow tables are simpler to query and type-check; a unified timeline can be a view later.
- Referee as an entity, referee country, assistant referees.
- Inferring tactical positions beyond the source's line grouping.

## Decisions

### Three tables, ordinal-keyed

```
lineup_entry   id uuid PK, match_id, side, ordinal, player_id NULL, player_name,
               role (STARTER|SUBSTITUTE), line_index NULL, is_captain
               UNIQUE (match_id, side, ordinal)
substitution   id uuid PK, match_id, side, ordinal, minute, added_minute NULL,
               player_off_id NULL, player_off_name, player_on_id NULL, player_on_name
               UNIQUE (match_id, side, ordinal)
card           id uuid PK, match_id, side, ordinal, minute, added_minute NULL,
               player_id NULL, player_name, kind (YELLOW|SECOND_YELLOW|RED)
               UNIQUE (match_id, side, ordinal)
match          + referee_name NULL, + attendance NULL
```

- **UUID PK + `(match_id, side, ordinal)` unique key**, mirroring v0.1's goal decision (UUID kept for future references; ordinal for idempotent upsert). Ordinal is source order within the side.
- **`(match_id, side, ordinal)` rather than `(match_id, player)`**: the player reference is nullable, and one player can have several cards.
- **`player_name` is always stored** (title-cased), even when `player_id` resolves — API responses never need a join to show a name, and an unresolved name is not lost.
- **Formation is derived, not stored**: computed from `line_index` counts at read time, so there's one source of truth.
- Alternative considered: delete-and-reinsert per match. Rejected for the same reason as in v0.1 — UUIDs would churn each sync.

### Parsing the lineup block

1. Join the team's lineup across continuation lines (indented lines until the next `<Team>:`, `Refs:`, or blank line).
1. Split line groups on `" - "` (space-dash-space). Hyphenated surnames (`DEWSBURY-HALL`, `ZAIRE-EMERY`) contain no surrounding spaces and are unaffected.
1. Within a group, split players on top-level commas (commas inside parentheses belong to substitution chains).
1. Each player token → name, optional `[c]`, zero or more card tags, optional parenthesised substitution `(<min>' <token>)`, recursively.
1. Card tags attach to the token they follow, so a card inside a substitution bracket belongs to the substitute.
1. Minutes parse as `<minute>(+<added>)?'`.

### Name handling

Reuse v0.1's capitalised-surname rule (title-case, split given/family only when the source marks it) and the case- and accent-insensitive squad matcher, scoped to the team-season's squad. Lineups resolve against the same squad file the v0.1 player ingest used, so resolution should be near-total; the unresolved fallback matches `goal.scorer_name`.

### Coverage

`coverage.events` is computed from the source configuration — the sync config marks which source files carry events — not inferred from row counts. A Club World Cup match with zero cards is still `full`.

### Added time

`minute` + `added_minute` (nullable) rather than a single integer or string, so `90+5'` sorts and filters correctly and differs from `95'` in extra time. Same representation as v0.1 goals, so the minute parser is shared.

## Risks / Trade-offs

- [Source line grouping is not a true formation; the Chelsea final reads as 5-3-2] → Spec says formation reflects source grouping; the API description says so too.
- [A malformed lineup line would fail the whole file] → Parse errors fail sync with file and line, consistent with v0.1's unknown-team rule; golden-file tests cover all 63 matches.

## Migration Plan

Additive only: one Alembic migration creating three tables and two nullable `match` columns. Rollback is a downgrade dropping them; no v0.1 data is touched.
