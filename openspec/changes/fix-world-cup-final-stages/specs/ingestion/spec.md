## RENAMED Requirements

- FROM: `### Requirement: Headings renamed to rounds`
- TO: `### Requirement: Headings renamed by the seed`

## MODIFIED Requirements

### Requirement: Headings renamed by the seed

A season seeded with `rounds` SHALL read the matches under each listed heading as the round label given for it, and take their stage from that label. Matching is case-insensitive and on a whole heading. For a Wikipedia season a heading is a section heading above a match box. For an openfootball season it is a part of the round label, which joins the file's headings with `/`. A listed heading that no match has SHALL fail the season, so a moved pin or an edited file can't silently stop renaming a round. A season read from results grids SHALL reject the field.

#### Scenario: Tournament played as one round robin

- **GIVEN** the 1916 South American Championship, whose boxes sit under `Results`, seeded with `rounds: {Results: Group stage}`
- **WHEN** it is synced
- **THEN** its matches have stage `GROUP` with no group name, and form one table of four teams

#### Scenario: Final round that is a group

- **GIVEN** the 1989 Copa América, whose four-team final round sits under `Final round`, seeded with `rounds: {Final round: Second group stage}`
- **WHEN** it is synced
- **THEN** those matches have stage `GROUP` in phase 2, not `FINAL`

#### Scenario: openfootball final round that is a group

- **GIVEN** the 1950 World Cup, whose file lists its four-team final round under `Final Round`, seeded with `rounds: {Final Round: Second group stage}`
- **WHEN** it is synced
- **THEN** its six final-round matches have stage `GROUP` in phase 2, and form one table of four teams
- **AND** its first-round groups are unchanged

#### Scenario: Heading that isn't there

- **GIVEN** a season seeded with `rounds: {Results: Group stage}` that has no `Results` heading
- **WHEN** it is synced
- **THEN** the season fails with an error naming the heading

### Requirement: Open Football text-format parser

The system SHALL parse the Open Football text DSL used in the league repositories (e.g. `openfootball/england`).

The parser handles, at minimum:

- matchday headers (`Matchday N`, `Regular Season - N`, `Round of 16`, `Final`, etc.)
- cup round headers (`Round N`, `N. Round`, `N. Runde`, `1st Round`, `First round`, `Preliminary round`, `Quarterfinals`, `Semi-finals`, etc.)
- group headers in English or German (`Group A`, `Gruppe G`, `Gruppe 1`) and placement matches (`Match for fifth place`, `5th Place`, `Bronze final`)
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

#### Scenario: Bronze final

- **WHEN** the header `Bronze final` (World Cup 2026) is parsed
- **THEN** it maps to stage `THIRD_PLACE`, not `FINAL`
