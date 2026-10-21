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

- matchday headers (`Matchday N`, `Regular Season - N`, `Round of 16`, `Final`, etc.)
- cup round headers (`Round N`, `N. Round`, `N. Runde`, `1st Round`, `First round`, `Preliminary round`, `Quarterfinals`, `Semi-finals`, etc.)
- group headers in English or German (`Group A`, `Gruppe G`, `Gruppe 1`) and placement matches (`Match for fifth place`, `5th Place`)
- date markers, with or without a weekday (`Fri Aug 15`, `June 14`, `Jun 14 2016`), on their own line or at the start of a match line, optionally followed by a kickoff time and a venue (`June 10 @ Düsseldorf  West Germany 1-1 Italy`, `Jul 1  21:45  Argentina 1-1 Bolivia`)
- match lines with home team, away team, and final score
- comments (lines starting with `#`) and blank lines
- team-name aliases (e.g. `Man United` → `Manchester United`)

#### Scenario: Unknown team name produces an explicit error

- **GIVEN** a match line referencing a team not present in the alias map nor the database
- **WHEN** the parser processes the line
- **THEN** sync fails with a clear error identifying the file path, line number, and unresolved team name
- **AND** no partial writes are committed for that file

#### Scenario: Numbered round headers

- **WHEN** the headers `Round 3`, `2. Round` and `10. Runde` are parsed
- **THEN** they map to stage `ROUND` with numbers 3, 2 and 10

#### Scenario: Preliminary round

- **WHEN** the header `Preliminary round` is parsed
- **THEN** it maps to stage `PRELIMINARY` with no number

#### Scenario: Unrecognised round header

- **WHEN** a header matches no stage rule
- **THEN** the season's sync fails with an error naming the label, and the other seasons are synced

#### Scenario: Date at the start of a match line

- **GIVEN** the line `June 10 @ Düsseldorf     West Germany     1-1 Italy` in a file for 1988
- **WHEN** it is parsed
- **THEN** it is a match West Germany v Italy on 1988-06-10, 1–1, at venue city Düsseldorf

#### Scenario: German group header

- **WHEN** the header `Gruppe G` is parsed
- **THEN** it maps to stage `GROUP`

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

#### Scenario: Sync and verify several leagues

- **WHEN** the sync is run with `--competition` for the Premier League, Bundesliga, Serie A and Ligue 1, and `--verify`
- **THEN** the four leagues are synced and then every configured season that names an article is verified

#### Scenario: Verify requested for a competition without a reference

- **WHEN** the sync is run with `--competition Q18756 --verify` (UEFA Champions League)
- **THEN** the Champions League is synced and no verification is attempted

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

### Requirement: Year-scoped team spellings

A `seeds/teams.yaml` spelling MAY apply only from or until a season's start year (`{name: "Yugoslavia", until: 1992}`). A source name SHALL resolve to the team of its plain spelling, or else to the one year-scoped spelling of that name whose years cover the season. Spellings of one name SHALL NOT overlap in years, nor be both plain and year-scoped; the seed load fails otherwise.

#### Scenario: Same name, two teams

- **GIVEN** `Yugoslavia` is the 1920–1992 team until 1992 and FR Yugoslavia (Serbia and Montenegro) from 1993
- **WHEN** the 1990 and 1998 World Cups sync
- **THEN** the 1990 matches belong to Yugoslavia and the 1998 matches to Serbia and Montenegro

### Requirement: Listings follow their team

A spelling removed from a `seeds/teams.yaml` entry SHALL no longer name its team. Matches and squad players whose listing then resolves to another team SHALL follow it and keep their UUIDs.

#### Scenario: Matches and players follow a re-scoped spelling

- **GIVEN** the 1998 World Cup synced while `Yugoslavia` was a plain spelling of the 1920–1992 team
- **WHEN** the spelling becomes year-scoped and sync runs
- **THEN** the 1998 Yugoslavia matches and squad players belong to Serbia and Montenegro, with the same UUIDs

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
