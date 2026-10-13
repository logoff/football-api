# Spec Delta

## MODIFIED Requirements

### Requirement: Open Football text-format parser

The system SHALL parse the Open Football text DSL used in the league repositories (e.g. `openfootball/england`).

The parser handles, at minimum:

- matchday headers (`Matchday N`, `Regular Season - N`, `Round of 16`, `Final`, etc.)
- cup round headers (`Round N`, `N. Round`, `N. Runde`, `Preliminary round`, `Quarterfinals`, `Semi-finals`, etc.)
- date markers
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
