# Spec Delta

## ADDED Requirements

### Requirement: Unchanged seasons are not re-verified

After a complete verification of a season, the system SHALL store the title and revision ID of every reference page it read. Without `--full`, a season SHALL be verified again only when it was synced in the same run, has no complete verification stored for its current data, has a page whose current revision differs (or that now redirects elsewhere or no longer exists), or is due in the rotation.

#### Scenario: Nothing changed

- **GIVEN** a season verified on the previous run, not synced in this run, and whose pages have the same revisions
- **WHEN** verification runs, and the season isn't due in the rotation
- **THEN** the season's article isn't fetched
- **AND** its statuses and `checked_at` are unchanged

#### Scenario: Article edited

- **GIVEN** a season whose article has a new revision since its last verification
- **WHEN** verification runs
- **THEN** the season is verified again and its statuses follow the new article

#### Scenario: Sub-article edited

- **GIVEN** a tournament season whose group sub-article has a new revision
- **WHEN** verification runs
- **THEN** the season is verified again

#### Scenario: Season re-synced

- **GIVEN** a season whose data changed and was re-synced in this run
- **WHEN** verification runs
- **THEN** the season is verified again, whatever its pages' revisions

### Requirement: Verification rotation

A season whose last complete verification is more than seven days old SHALL be verified again, even when nothing visible changed. Each run SHALL take at most a seventh of its verifiable seasons (rounded up) this way, oldest first.

#### Scenario: Check older than a week

- **GIVEN** a season last verified eight days ago, in which nothing changed
- **WHEN** verification runs
- **THEN** the season is verified again

#### Scenario: Recent check

- **GIVEN** a season verified yesterday, in which nothing changed
- **WHEN** verification runs
- **THEN** the season isn't verified again

#### Scenario: Many checks due at once

- **GIVEN** 227 verifiable seasons, all last verified eight days ago, in which nothing changed
- **WHEN** verification runs
- **THEN** the 33 with the oldest checks are verified again, and the others on later runs

### Requirement: Incomplete verification keeps its state

A verification that doesn't complete SHALL NOT update the stored titles, revisions or time, so the season is due again on the next run.

#### Scenario: Reference unavailable

- **GIVEN** a season due for verification whose article can't be fetched
- **WHEN** verification runs
- **THEN** its statuses are unchanged and it is due again on the next run

## MODIFIED Requirements

### Requirement: Reference content is never stored or served

The system SHALL NOT store, serve or change match data from the reference. Only the status, the reference's name and the time of the check SHALL be persisted, and, for deciding when to verify again, the titles and revision IDs of the reference pages read. Titles and revision IDs SHALL NOT be served.

#### Scenario: Mismatch leaves no reference data behind

- **GIVEN** a match marked `MISMATCH`
- **WHEN** a client GETs the match
- **THEN** the response contains the stored score and the verification status
- **AND** contains no score or other value taken from the reference

### Requirement: Disagreement report

Each verification run SHALL log one line per `MISMATCH` and `SOURCE_BEHIND` match (season, teams, stored and reference score) and a summary with the count of each status per season. A season that isn't verified again SHALL log the same summary from its stored statuses, marked as unchanged, and one line per stored `MISMATCH` and `SOURCE_BEHIND` match with the stored score and the date of its last check in place of the reference score.

#### Scenario: Summary after a run

- **WHEN** verification for La Liga finishes
- **THEN** the log contains, for each configured season, the number of `VERIFIED`, `MISMATCH`, `UNCONFIRMED` and `SOURCE_BEHIND` matches

#### Scenario: Mismatch is listed

- **GIVEN** a match marked `MISMATCH`
- **WHEN** verification finishes
- **THEN** the log has a line naming the season, both teams, the stored score and the reference score

#### Scenario: Mismatch in an unchanged season

- **GIVEN** a match marked `MISMATCH` in a season that isn't verified again
- **WHEN** verification finishes
- **THEN** the log has a line naming the season, both teams and the stored score, in the same format up to the stored score, and the season's summary is marked as unchanged
