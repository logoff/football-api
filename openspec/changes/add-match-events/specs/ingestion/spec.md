# Spec Delta

## MODIFIED Requirements

### Requirement: Idempotency

All ingestion writes SHALL be idempotent: re-running sync with no source-data changes SHALL produce a database state byte-for-byte equivalent to the prior state for the rows it manages.

Reconciliation order — when ingesting an entity from a source record carrying `(source, source_id)`:

1. **Look up by `external_ref(source, source_id)`.** If a canonical UUID is found, reuse it.
1. **Else look up by the entity's natural key** (below). If found, reuse the canonical UUID and write a new `external_ref` row linking the source to it.
1. **Else create a new canonical row** and write the `external_ref` row.

Natural keys for step 2:

- competitions — none beyond step 1: competitions are created only from `seeds/competitions.yaml` and matched through their Wikidata QID
- seasons — `(competition_id, label)`
- teams — none beyond step 1: teams are created only from `seeds/teams.yaml` and matched through their Open Football spellings and Wikidata QID. A spelling listed under one entry that still points at the team another entry claims through its QID has moved: its reference is released first, so the entry it moved to resolves to its own team. A team's Wikidata reference is the one its entry names; a corrected QID replaces the old one
- players — `(team_id, season_id, display_name)`, created only from squad files
- venues — `(name, city)`
- matches — `(season_id, stage, home_team_id, away_team_id, occurrence)`; kickoff is an attribute, not part of the key. A source match with no row under that key reuses a match of the same season, teams and date (within a day) that this sync hasn't matched yet, so a relabelled round keeps its UUID. Failing that, the match the same source listing (file, stage and spellings) was synced to follows the listing to its new teams, keeping its UUID. After a season syncs, teams that no longer play in it leave the season, and matches of that season the source no longer lists are deleted, with their goals, lineup entries, substitutions, cards, verification status and external references
- goals — `(match_id, ordinal)`; goals have no `external_ref` rows, and ordinals beyond the source's goal count are deleted
- lineup entries, substitutions and cards — `(match_id, side, ordinal)`; like goals, they have no `external_ref` rows, and ordinals beyond the source's count for that side are deleted

No source is privileged in this algorithm: the same reconciliation flow applies whether the inbound record came from Wikidata, Open Football, or any future source.

#### Scenario: Unchanged sources produce an unchanged database

- **GIVEN** a database after a successful sync
- **WHEN** sync runs again with no source-data changes
- **THEN** every managed row, including every UUID, is identical to before

#### Scenario: Goal list shrinks after a source correction

- **GIVEN** a match synced with 3 goals (ordinals 1–3)
- **WHEN** the source is corrected to list 2 goals and sync runs
- **THEN** goals with ordinals 1 and 2 keep their UUIDs and are updated in place
- **AND** the goal with ordinal 3 is deleted

#### Scenario: Round relabelled in the source

- **GIVEN** a synced Coupe de France season whose round headed `10. Runde` (stage `ROUND`) is renamed `Round of 32` in the source
- **WHEN** sync runs
- **THEN** those matches keep their UUIDs, now with stage `R32`
- **AND** the season has the same number of matches as before

#### Scenario: Match removed from the source

- **GIVEN** a synced season and a source correction that removes one match
- **WHEN** sync runs
- **THEN** that match, its goals, its events and its verification status are deleted
- **AND** every other match keeps its UUID

#### Scenario: Spelling moved to its own club

- **GIVEN** a synced database where `Liverpool (URU)` was listed under Liverpool F.C. of England
- **WHEN** `seeds/teams.yaml` moves it to a new entry for Liverpool F.C. (Montevideo) and sync runs
- **THEN** a team row for the Montevideo club exists, and the matches listed with that spelling point at it, keeping their UUIDs
- **AND** Liverpool F.C. of England keeps its UUID, no longer has the moved spelling, and leaves the seasons it only played through it

#### Scenario: Corrected Wikidata QID

- **GIVEN** a team synced with a wrong QID
- **WHEN** its entry is corrected and sync runs
- **THEN** the team keeps its UUID and its only Wikidata reference is the corrected QID
