## ADDED Requirements

### Requirement: Seasons sourced from the reference are not verified

A season whose source is Wikipedia SHALL NOT be verified against Wikipedia, and its matches SHALL get no verification status. The seed load SHALL fail for such a season if it also names a verification article.

#### Scenario: Wikipedia season

- **GIVEN** European Cup 1975-76, sourced from Wikipedia
- **WHEN** verification runs for the Champions League
- **THEN** no 1975-76 match gets a status, and 2011-12 onwards are verified as before

#### Scenario: Seed names both

- **GIVEN** a season seeded with `wikipedia_source` and `wikipedia`
- **WHEN** the seeds load
- **THEN** the load fails, naming the season

## MODIFIED Requirements

### Requirement: Reference content is never stored or served

The system SHALL NOT store, serve or change match data from the reference. Only the status, the reference's name and the time of the check SHALL be persisted, and, for deciding when to verify again, the titles and revision IDs of the reference pages read. Titles and revision IDs SHALL NOT be served. This applies to the verification reference only. A season whose own source is Wikipedia stores and serves the data read from its pinned revisions (see `season-sources`).

#### Scenario: Mismatch leaves no reference data behind

- **GIVEN** a match marked `MISMATCH`
- **WHEN** a client GETs the match
- **THEN** the response contains the stored score and the verification status
- **AND** contains no score or other value taken from the reference
