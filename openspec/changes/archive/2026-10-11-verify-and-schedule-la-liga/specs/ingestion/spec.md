# Spec Delta

## ADDED Requirements

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
