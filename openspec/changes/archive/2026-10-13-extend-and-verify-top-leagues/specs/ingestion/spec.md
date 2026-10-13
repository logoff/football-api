# Spec Delta

## MODIFIED Requirements

### Requirement: Verification after sync

The sync command SHALL accept `--verify`. With it, the synced competitions that have a verification reference are verified after a successful sync. Competitions without a reference are skipped silently.

#### Scenario: Sync and verify La Liga

- **WHEN** `python -m football_api.sync --competition Q324867 --verify` is run
- **THEN** La Liga is synced and then every configured La Liga season is verified

#### Scenario: Sync and verify several leagues

- **WHEN** the sync is run with `--competition` for the Premier League, Bundesliga, Serie A and Ligue 1, and `--verify`
- **THEN** the four leagues are synced and then every configured season that names an article is verified

#### Scenario: Verify requested for a competition without a reference

- **WHEN** the sync is run with `--competition Q18756 --verify` (UEFA Champions League)
- **THEN** the Champions League is synced and no verification is attempted
