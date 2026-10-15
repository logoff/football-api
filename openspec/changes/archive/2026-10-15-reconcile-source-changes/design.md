# Design

## Context

`sync_match` looks a match up by (season, stage, home, away, occurrence) and inserts it if there is none. Nothing removes matches. Goals and verification rows already cascade on match delete; `external_ref` has no foreign key.

## Goals / Non-Goals

**Goals:**

- Keep UUIDs through relabels.
- Never leave matches the source no longer has.

**Non-Goals:**

- Detecting a relabel and a reschedule of the same match together. That falls back to delete and insert, with a new UUID.

## Decisions

### D1. Relabel fallback

When the exact key misses, look for an unmatched match of the same season and teams whose kickoff date is within one day. The day of tolerance absorbs the UTC-midnight shift of date-only kickoffs.

If one is found, update its stage and occurrence, and replace its openfootball `external_ref` with the new key.

**Alternative:** keying matches by date. Rejected, because postponements change dates while the match stays the same.

### D2. Delete what the sync didn't see

Each season's sync collects the ids of the matches it matched or created. Afterwards it deletes the season's other matches and their `external_ref` rows; goals and verification rows cascade. This happens in the same per-season transaction, so a failed parse deletes nothing.

## Source coverage

**Integration run** (empty database):

1. Synced the Coupe de France from the files before openfootball/europe#13: 185 `ROUND`, 8 `R16`, 4 `QF`, 2 `SF`, 1 `FINAL`.
1. Pulled europe#13, which renames `10. Runde` to `Round of 32`, and synced again.
1. Result: 16 matches moved from `ROUND` to `R32` (each logged), every UUID is unchanged, and the season still has 200 matches.

## Risks / Trade-offs

- **[Risk] A source file truncated by mistake deletes matches.** → Parsing failures abort the season before any write. A file that parses but lost matches would be applied as the source says. The deletion count is logged per season, so a large drop is visible.
