# ingestion Specification

## Purpose

Bring data from external sources into the canonical schema, idempotently and on demand. v0.1 ingests from two sources: the `openfootball/*` GitHub repositories (primary data) and Wikidata (entity identifier seed).

## Requirements

### Requirement: On-demand sync

The system SHALL provide a single, idempotent sync command that, when invoked, pulls the latest data from configured sources and reconciles it into the database.

The command is `just sync`, which delegates to `python -m football_api.sync`. The recipe is defined in the project's `justfile`.

#### Scenario: First sync on an empty database

- **GIVEN** an empty database
- **WHEN** `just sync` is run
- **THEN** all in-scope competitions, seasons, teams, players, matches, and goals are populated
- **AND** the command exits 0

#### Scenario: Repeat sync on an already-populated database

- **GIVEN** a database previously populated by a successful sync
- **WHEN** `just sync` is run again with no source-data changes
- **THEN** no duplicate rows are created
- **AND** existing rows are unchanged or updated in place

### Requirement: Open Football text-format parser

The system SHALL parse the Open Football text DSL used in the league repositories (e.g. `openfootball/england`).

The parser handles, at minimum:

- matchday headers (`Matchday N`, `Round of 16`, `Final`, etc.)
- date markers
- match lines with home team, away team, and final score
- comments (lines starting with `#`) and blank lines
- team-name aliases (e.g. `Man United` → `Manchester United`)

#### Scenario: Unknown team name produces an explicit error

- **GIVEN** a match line referencing a team not present in the alias map nor the database
- **WHEN** the parser processes the line
- **THEN** sync fails with a clear error identifying the file path, line number, and unresolved team name
- **AND** no partial writes are committed for that file

### Requirement: Open Football JSON path

The system SHALL prefer reading from Open Football JSON mirrors (when available and current for the target season) over text parsing.

#### Scenario: JSON present and current

- **WHEN** a JSON file is found for the target competition-season under `openfootball/football.json` (or equivalent)
- **AND** the JSON file's coverage is current for the requested edition
- **THEN** ingestion reads from JSON in preference to the text DSL

### Requirement: Wikidata SPARQL seed

The Wikidata QIDs of competitions and teams SHALL come from the curated seed files and be stored as `external_ref` rows when the seeds are loaded, so entity identity never depends on Wikidata being reachable. The system SHALL then query the public Wikidata SPARQL endpoint to confirm that each seeded QID still exists, and log a warning for any that was deleted or merged.

#### Scenario: Wikidata endpoint unavailable

- **GIVEN** the Wikidata SPARQL endpoint returns 5xx or times out
- **WHEN** sync runs
- **THEN** the Wikidata phase logs an error and is skipped
- **AND** subsequent phases (Open Football) proceed using existing `external_ref` rows if any

### Requirement: Idempotency

All ingestion writes SHALL be idempotent: re-running sync with no source-data changes SHALL produce a database state byte-for-byte equivalent to the prior state for the rows it manages.

Reconciliation order — when ingesting an entity from a source record carrying `(source, source_id)`:

1. **Look up by `external_ref(source, source_id)`.** If a canonical UUID is found, reuse it.
1. **Else look up by the entity's natural key** (below). If found, reuse the canonical UUID and write a new `external_ref` row linking the source to it.
1. **Else create a new canonical row** and write the `external_ref` row.

Natural keys for step 2:

- competitions — none beyond step 1: competitions are created only from `seeds/competitions.yaml` and matched through their Wikidata QID
- seasons — `(competition_id, label)`
- teams — none beyond step 1: teams are created only from `seeds/teams.yaml` and matched through their Open Football spellings and Wikidata QID
- players — `(team_id, season_id, display_name)`, created only from squad files
- venues — `(name, city)`
- matches — `(season_id, stage, home_team_id, away_team_id)`; kickoff is an attribute, not part of the key
- goals — `(match_id, ordinal)`; goals have no `external_ref` rows, and ordinals beyond the source's goal count are deleted

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

### Requirement: Source attribution

For every entity ingested, the system SHALL record which source(s) contributed to it via `external_ref` rows.

#### Scenario: Auditing where a team came from

- **GIVEN** a team `Real Madrid` ingested first from Wikidata then enriched from Open Football
- **WHEN** an operator queries `external_ref` for that team
- **THEN** rows for both sources are present with their respective source IDs

### Requirement: Competition-scoped sync

The sync command SHALL accept `--competition <Wikidata QID>`, repeatable, to sync only those competitions. Without it, every configured competition is synced. An unknown QID SHALL fail the command before any database write.

#### Scenario: Sync only La Liga

- **WHEN** `python -m football_api.sync --competition Q324867` is run
- **THEN** only La Liga's configured seasons are pulled and reconciled
- **AND** other competitions' rows are unchanged

#### Scenario: Unknown competition

- **WHEN** the sync is run with `--competition Q1`
- **THEN** it exits non-zero with an error naming `Q1`
- **AND** nothing is written to the database

### Requirement: Verification after sync

The sync command SHALL accept `--verify`. With it, the synced competitions that have a verification reference are verified after a successful sync. Competitions without a reference are skipped silently.

#### Scenario: Sync and verify La Liga

- **WHEN** `python -m football_api.sync --competition Q324867 --verify` is run
- **THEN** La Liga is synced and then every configured La Liga season is verified

#### Scenario: Verify requested for a competition without a reference

- **WHEN** the sync is run with `--competition Q9448 --verify` (Premier League)
- **THEN** the Premier League is synced and no verification is attempted

### Requirement: Unattended runs

The sync command SHALL be safe to run unattended on a schedule. It SHALL exit 0 when every requested competition synced, even if verification found mismatches or its reference was unavailable. It SHALL exit non-zero when any requested competition failed to sync, after syncing the others. It SHALL log one summary line per competition and season.

#### Scenario: Mismatches don't fail the run

- **GIVEN** verification finds a `MISMATCH`
- **WHEN** the scheduled sync finishes
- **THEN** it exits 0

#### Scenario: One season fails to parse

- **GIVEN** one configured season's source file can't be parsed
- **WHEN** the sync runs
- **THEN** the other seasons are synced and committed
- **AND** the failing season has no partial writes
- **AND** the command exits non-zero

#### Scenario: Database schema behind the code

- **GIVEN** a database whose migrations are older than the running code
- **WHEN** the sync starts
- **THEN** it exits non-zero without writing, with an error saying the schema must be migrated first

#### Scenario: Concurrent runs

- **GIVEN** a sync is already running against the database
- **WHEN** a second sync starts
- **THEN** the second one exits non-zero without writing, with an error saying a sync is in progress

### Requirement: Configurable sources directory

The sync SHALL clone and update sources under the directory set by the `SOURCES_DIR` setting, so a read-only container can point it at a writable volume. The published container image SHALL be able to run the sync.

#### Scenario: Sync from the container image

- **GIVEN** the published image, with `SOURCES_DIR` set to a writable empty directory and `DATABASE_URL` set
- **WHEN** `python -m football_api.sync --competition Q324867 --verify` is run as the container command
- **THEN** sources are cloned into that directory and the sync and verification complete
