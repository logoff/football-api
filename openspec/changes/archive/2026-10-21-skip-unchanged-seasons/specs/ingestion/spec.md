# Spec Delta

## ADDED Requirements

### Requirement: Unchanged seasons are skipped

A season whose inputs (the code, its seed entries, `seeds/teams.yaml` and every source file it reads) are unchanged since its last successful sync SHALL NOT be re-synced, and SHALL log one line saying it is unchanged, with its match count. A season that fails to sync SHALL be synced again on the next run.

#### Scenario: Nothing changed

- **GIVEN** a database after a successful sync
- **WHEN** the sync runs again with the same sources, seeds and code
- **THEN** no season is re-synced
- **AND** every season logs that it is unchanged, with its match count
- **AND** the command exits 0

#### Scenario: Upstream correction to one season

- **GIVEN** a database after a successful sync
- **WHEN** openfootball corrects a score in one season's file and the sync runs
- **THEN** only that season is re-synced, and the corrected score is stored

#### Scenario: Seed or code change

- **GIVEN** a database after a successful sync
- **WHEN** `seeds/teams.yaml` or the code changes and the sync runs
- **THEN** every season is re-synced

#### Scenario: Squad or events file changes

- **GIVEN** a season with a squads or events file
- **WHEN** only that file changes and the sync runs
- **THEN** the season is re-synced

#### Scenario: A failed season is retried

- **GIVEN** a season whose sync failed on the previous run
- **WHEN** the sync runs again with the same sources
- **THEN** the season is synced again

### Requirement: Forced full sync

The sync command SHALL accept `--full`, which re-syncs every requested season whether or not its inputs changed.

#### Scenario: Forced full run

- **WHEN** the sync is run with `--full`
- **THEN** every requested season is re-synced, whatever its stored fingerprint
