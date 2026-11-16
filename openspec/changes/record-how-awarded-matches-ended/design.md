# Design

## Context

The parser turns openfootball's `[awarded]` tag into `awarded: true` on a `COMPLETED` match, and keeps whatever score the line has. `seeds/standings.yaml` already curates one fact about awarded matches: the winner of the ones recorded with a level score (`awards`, keyed by competition, season and the two teams' QIDs). Today's sources have 42 awarded matches: Reus's 21 in Segunda División 2018-19 (#47) and 21 more across 15 seasons. Every team involved has a QID.

## Goals / Non-Goals

**Goals:**

- Say, for every `COMPLETED` match, whether it was played in full, in part or not at all.
- Curate the 42 awarded matches, each with a source.

**Non-Goals:**

- The score at the moment of abandonment, or the on-pitch score of a match later overturned. The stored score stays whatever the source records.
- A `played` filter on `/v1/matches`. It's easy to add later if anyone asks for it.
- Moving `standings.yaml`'s `awards` into the new seed. They answer a different question (who won), for the standings.

## Decisions

### D1. A `played` field, not a new status

`played` is `FULL`, `PARTIAL` or `NONE` on every `COMPLETED` match, and null otherwise.

- **Alternative: a status `AWARDED` or `WALKOVER`.** Rejected. Clients that count `COMPLETED` matches, and the standings, would have to learn a new status. An awarded match is still a result that counts.
- **Alternative: an enum only on awarded matches (`awarded_after`).** Rejected. `played` answers the same question for every match, and for a match that isn't awarded the answer is always `FULL`. So no client needs to check `awarded` first.

### D2. `seeds/awarded.yaml`

```yaml
matches:
  - competition: Q13394
    season: "2016-17"
    home: Q208399 # SC Bastia
    away: Q704 # Olympique Lyonnais
    played: PARTIAL
    reason: "Abandoned at half-time after Bastia supporters attacked Lyon players"
    source: https://…
teams:
  - competition: Q35615
    season: "2018-19"
    team: Q1387573 # CF Reus Deportiu
    from: 2019-01-19
    played: NONE
    reason: "Expelled by LaLiga; every remaining fixture awarded 1–0 to the opponent"
    source: https://…
```

- **Match entries** use the key `standings.yaml` uses. When a pairing occurs more than once in a season, the entry applies only to the awarded one: a match without the `[awarded]` tag is always `FULL`.
- **Team entries** cover every awarded match of that team on or after `from`. A match entry wins over a team entry.
- **Validation at load:** every competition, season and QID must be seeded, as for `standings.yaml`. Two entries for the same match are an error, and so is a match entry for a match a team entry already covers with the same value.
- **Alternative: one entry per Reus match.** Rejected. 21 entries with the same reason and source say less than one.

### D3. A missing entry warns and doesn't fail

A new `[awarded]` tag upstream would otherwise stop the scheduled sync until someone edits the seed. Instead, sync stores `played: null` and logs a warning naming the competition, season and match. Null means "not known", which is honest. Unknown team spellings fail the sync because they would break identity. A missing `played` breaks nothing.

### D4. Storage

A nullable column `match.played` (a Postgres enum, like `status`), set during the match upsert from the parsed match and the seed. Changing the seed changes the stored value on the next sync, even for a season whose source is unchanged. So the season fingerprint (`season_check`) also covers that season's entries in the seed, the way it already covers the teams seed.

## Risks / Trade-offs

- **Curation needs a source per match.** Where no official one exists, the entry cites the best available source and says so in a comment, as the Reus points adjustment does. A match with no reliable source stays out of the seed and keeps `played: null`.
- **`PARTIAL` with a level score** (Bastia v Lyon 0–0) still reads oddly next to `awarded`. The README explains that the score is the one at abandonment.
