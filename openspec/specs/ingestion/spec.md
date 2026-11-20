# ingestion Specification

## Purpose

Bring data from external sources into the canonical schema, idempotently and on demand. Match data comes from the `openfootball/*` GitHub repositories and, for seasons they lack, from pinned revisions of English Wikipedia articles; Wikidata seeds entity identifiers.

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

A season whose inputs (the code, its seed entries, `seeds/teams.yaml`, every source file it reads, and the revision IDs it is pinned to) are unchanged since its last successful sync SHALL NOT be re-synced, and SHALL log one line saying it is unchanged, with its match count. A season that fails to sync SHALL be synced again on the next run.

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

#### Scenario: Pin moved

- **GIVEN** a Wikipedia season after a successful sync
- **WHEN** one of its pins moves to another revision and the sync runs
- **THEN** only that season is re-synced

### Requirement: Forced full sync

The sync command SHALL accept `--full`, which re-syncs every requested season whether or not its inputs changed.

#### Scenario: Forced full run

- **WHEN** the sync is run with `--full`
- **THEN** every requested season is re-synced, whatever its stored fingerprint

### Requirement: Wikipedia season source

A season seeded with `wikipedia_source` SHALL be read from the match boxes, or for a league season the results grids, of the English Wikipedia pages it lists, each pinned to a revision ID, and SHALL NOT be read from the live pages. The pages are the season article and the sub-articles it needs. Each box is used once. A season seeded with both a Wikipedia source and an openfootball file SHALL fail the seed load.

#### Scenario: Season read from pinned revisions

- **GIVEN** European Cup 1955-56 pinned to revision 1384458360 of `1955–56 European Cup`
- **WHEN** the sync runs
- **THEN** the season has the 29 matches of that revision's boxes, each `COMPLETED` with its date and score

#### Scenario: Article edited after pinning

- **GIVEN** a pinned season whose article has since been edited on Wikipedia
- **WHEN** the sync runs
- **THEN** the stored matches still come from the pinned revision

#### Scenario: Unrelated sub-articles

- **GIVEN** the article `1960–61 European Cup`, which links `1960–61 European Cup Winners' Cup`
- **WHEN** its pins are written
- **THEN** the Winners' Cup article is not pinned, and none of its matches are stored in the European Cup season

#### Scenario: League season read from its results grid

- **GIVEN** La Liga 1929 pinned to a revision of `1929 La Liga`, whose results grid has 10 clubs
- **WHEN** the sync runs
- **THEN** the season has 90 `COMPLETED` matches with stage `LEAGUE`, one per filled cell, each with its score and no date
- **AND** the two relegation play-off boxes on the same page are not stored

### Requirement: Pinned revisions are cached

A pinned revision SHALL be fetched from Wikipedia at most once and kept under `SOURCES_DIR`. If a revision can't be fetched, that season's sync SHALL fail and leave its stored data as it was, as for a source file that can't be parsed.

#### Scenario: Second sync

- **GIVEN** a sync that fetched every pinned revision
- **WHEN** the sync runs again with the same pins
- **THEN** no request is sent to Wikipedia for those revisions

#### Scenario: Wikipedia unreachable

- **GIVEN** a season whose pin moved to a revision that isn't cached
- **WHEN** the sync runs and Wikipedia can't be reached
- **THEN** that season fails, its stored matches are unchanged, and the other seasons sync

### Requirement: Stage from section headings

Each match box SHALL take its stage, and its group or round number where there is one, from the section heading above it: preliminary round, numbered round, group, quarter-finals, semi-finals, third place (`Third place play-off`, `Third-place match`), final (`Final`, `Finals`), and their variants. A replay or play-off of a tie SHALL keep the stage of that tie. A heading that only wraps rounds (`Knockout phase`, `Final phase`, `Tournament phase`, `Qualifying phase`) SHALL name no stage, so the round under it decides. A box under a heading that maps to no stage SHALL fail the season.

#### Scenario: Numbered rounds and groups

- **GIVEN** boxes under `First round`, `Group B` and `Quarter-finals`
- **WHEN** they are read
- **THEN** their stages are `ROUND` with matchday 1, `GROUP` with group `B`, and `QF`

#### Scenario: Unknown heading

- **GIVEN** a box under the heading `Trivia`
- **WHEN** the season is synced
- **THEN** the season fails with an error naming the page, revision and heading

#### Scenario: Round under a phase wrapper

- **GIVEN** the 1999–2000 UEFA Cup box under `Final phase / Third round`
- **WHEN** it is read
- **THEN** its stage is `ROUND` with matchday 3, not `FINAL`

#### Scenario: Two-legged final

- **GIVEN** the 1975 Copa América boxes under `Knockout stage / Finals`: two legs and a play-off
- **WHEN** they are read
- **THEN** all three have stage `FINAL`

#### Scenario: Third-place match

- **GIVEN** the 1993 Copa América box under `Knockout stage / Third-place match`
- **WHEN** it is read
- **THEN** its stage is `THIRD_PLACE`

### Requirement: Teams resolved by Wikidata QID

A team in a Wikipedia season SHALL resolve through the Wikidata QID of the club article its box links, to the team seeded with that QID or listing it under `reference_wikidata`. A club the box links to an article with no QID SHALL take the QID the season seed gives for that title (`wikipedia_qids`). Otherwise, a box linking an article with no QID, or a QID that no team is seeded with, SHALL fail the season, as an unknown spelling does.

#### Scenario: Known club

- **GIVEN** a box linking `Real Madrid CF`, whose QID is Q8682
- **WHEN** it is read
- **THEN** the match's team is the team seeded with Q8682, the same one the openfootball seasons use

#### Scenario: Club not seeded

- **GIVEN** a box linking a club whose QID no team in `seeds/teams.yaml` has
- **WHEN** the season is synced
- **THEN** the season fails with an error naming the article and the QID

#### Scenario: Club article that doesn't exist

- **GIVEN** the 1996–97 UEFA Cup, whose box links `Khazri Buzovna`, an article that doesn't exist, and a season seed giving `Khazri Buzovna: Q2338519`
- **WHEN** it is synced
- **THEN** the match's team is the team seeded with Q2338519

### Requirement: Walkovers

A box with no result (`w/o`, `Walkover`, or a tie a club withdrew from) SHALL be stored `CANCELLED` without a score. A box marked awarded SHALL be stored `COMPLETED`, flagged `awarded`, with the score it gives.

#### Scenario: Withdrawal

- **GIVEN** the 1961-62 box Linfield v Vorwärts Berlin (article `1. FC Frankfurt`), which gives no result
- **WHEN** it is read
- **THEN** the match is `CANCELLED` and has no score

#### Scenario: Awarded

- **GIVEN** the 2004-05 box Roma 0–3 Dynamo Kyiv (awd.)
- **WHEN** it is read
- **THEN** the match is `COMPLETED`, `awarded`, 0–3

### Requirement: Results grid cells

Each cell of a results grid SHALL give one match: the club of its row at home, the club of its column away, and the cell's score. Rows and columns SHALL pair by position, so the diagonal is skipped even where a row and its column name the club differently. An empty cell SHALL be stored `CANCELLED` without a score.

#### Scenario: Row and column named differently

- **GIVEN** the 1946-47 grid, whose row says `Atlético Bilbao` and whose column says `Athletic Bilbao`, both resolving to one QID
- **WHEN** it is read
- **THEN** the season has 182 matches and no club plays itself

#### Scenario: Row and column that don't match

- **GIVEN** a grid whose row and column at the same position resolve to different QIDs
- **WHEN** the season is synced
- **THEN** the season fails with an error naming the page, revision and both clubs

#### Scenario: Annulled match

- **GIVEN** the 1979-80 grid, whose Málaga v Salamanca cell is empty
- **WHEN** it is read
- **THEN** that match is `CANCELLED` without a score, and the other 305 are `COMPLETED`

### Requirement: Grid sections

A season read from grids SHALL read the one grid on its pages when there is only one. When there are several, the season seed SHALL name the top-level section of each grid to read, and every grid whose top-level section is named is read. A page with several grids and no sections named, or a named section with no grid, SHALL fail the season. The stage and group SHALL come from the section heading, as for match boxes.

#### Scenario: Second phase in groups

- **GIVEN** La Liga 1986-87 seeded with the sections `Regular season`, `Championship group`, `Intermediate group` and `Relegation group`
- **WHEN** it is synced
- **THEN** the season has 306 `LEAGUE` matches and 90 `GROUP` matches, 30 in each of three groups

#### Scenario: Grid of another competition on the page

- **GIVEN** La Liga 1950-51, whose page also has a relegation group grid with Segunda clubs, seeded with the section `Results` only
- **WHEN** it is synced
- **THEN** the season has the 240 matches of the league grid and none of the relegation group

#### Scenario: Several grids and no sections

- **GIVEN** a season whose pinned page has two grids and whose seed names no section
- **WHEN** the season is synced
- **THEN** the season fails with an error naming the page, revision and the headings of the grids

### Requirement: Awarded matches from the seed

A grid can't mark a match as awarded, and a match box can give the score without saying the match was awarded. In a season read from Wikipedia, a match listed in `seeds/awarded.yaml` SHALL be stored flagged `awarded`, with the score the grid or box gives and the curated `played` value. An entry for a pairing the season doesn't have SHALL fail that season's sync.

#### Scenario: Awarded match from the seed

- **GIVEN** La Liga 1979-80, and an `awarded.yaml` entry for Málaga v Almería curated as `NONE`
- **WHEN** it is synced
- **THEN** that match is `COMPLETED`, `awarded` and `played` `NONE`, with the grid's score

#### Scenario: Box that doesn't say the match was awarded

- **GIVEN** the 1942 South American Championship, whose box for Argentina v Chile reads 0–0 with no mark, and an `awarded.yaml` entry for it curated as `PARTIAL`
- **WHEN** it is synced
- **THEN** that match is `COMPLETED`, `awarded` and `played` `PARTIAL`, with the score 0–0

### Requirement: Sections left out

A Wikipedia season seeded with `wikipedia_skip` SHALL read no box under a section whose heading is one of those listed. A listed section that the pinned pages don't have SHALL fail the season, so a moved pin can't silently stop leaving a round out.

#### Scenario: Qualifying round left out

- **GIVEN** the 1997–98 UEFA Cup seeded with `wikipedia_skip: [First qualifying round, Second qualifying round]`
- **WHEN** it is synced
- **THEN** the season has the matches from the first round to the final, and none of the qualifying rounds

#### Scenario: Section that isn't there

- **GIVEN** a season seeded with `wikipedia_skip: [Preliminary round]` whose pinned pages have no such section
- **WHEN** it is synced
- **THEN** the season fails with an error naming the section

### Requirement: Headings renamed to rounds

A Wikipedia season seeded with `wikipedia_rounds` SHALL read the boxes under each listed heading as the round label given for it, and take their stage from that label. A listed heading that the pinned pages don't have SHALL fail the season, so a moved pin can't silently stop renaming a round.

#### Scenario: Tournament played as one round robin

- **GIVEN** the 1916 South American Championship, whose boxes sit under `Results`, seeded with `wikipedia_rounds: {Results: Group stage}`
- **WHEN** it is synced
- **THEN** its matches have stage `GROUP` with no group name, and form one table of four teams

#### Scenario: Final round that is a group

- **GIVEN** the 1989 Copa América, whose four-team final round sits under `Final round`, seeded with `wikipedia_rounds: {Final round: Second group stage}`
- **WHEN** it is synced
- **THEN** those matches have stage `GROUP` in phase 2, not `FINAL`

#### Scenario: Heading that isn't there

- **GIVEN** a season seeded with `wikipedia_rounds: {Results: Group stage}` whose pinned pages have no `Results` section
- **WHEN** it is synced
- **THEN** the season fails with an error naming the heading

### Requirement: Abandoned matches replayed

A Wikipedia season seeded with `wikipedia_abandoned` SHALL store each listed match (date, home and away QIDs) as `CANCELLED` without a score, since it was replayed and the replay is the result. A listed match that no box holds SHALL fail the season.

#### Scenario: 1916 Argentina v Uruguay

- **GIVEN** the 1916 South American Championship, whose boxes include Argentina v Uruguay on 16 July, abandoned at 0–0, and its replay on 17 July, with the first listed under `wikipedia_abandoned`
- **WHEN** it is synced
- **THEN** the 16 July match is `CANCELLED` without a score
- **AND** the table counts the 17 July match, so each team has played 3
