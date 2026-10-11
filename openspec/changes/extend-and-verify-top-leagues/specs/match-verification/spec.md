# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: Reference results for La Liga`
- TO: `### Requirement: Reference results for domestic leagues`

## MODIFIED Requirements

### Requirement: Reference results for domestic leagues

The system SHALL use the results grid of the English Wikipedia article named by each configured domestic league season as the verification reference. A season that names no article is not verified. Reference teams SHALL be matched to stored teams only through their Wikidata QID.

#### Scenario: Grid resolved for a configured season

- **GIVEN** La Liga 2025-26 is a configured season
- **WHEN** verification runs for La Liga
- **THEN** the reference results are read from the 2025–26 La Liga article's results grid
- **AND** each grid team is identified by the Wikidata QID of the article it links to

#### Scenario: Article reached through a redirect

- **GIVEN** a season names an article title that redirects, such as `2000–01 Premier League` (redirects to `2000–01 FA Premier League`)
- **WHEN** verification runs for that season
- **THEN** the grid of the redirect target is used and its scores are compared

#### Scenario: Season without an article

- **GIVEN** Serie A 2018-19 names no article
- **WHEN** verification runs for Serie A
- **THEN** that season is skipped without a warning and its matches have no status
- **AND** the other Serie A seasons are verified

#### Scenario: Reference team without a known QID

- **GIVEN** a grid team whose linked article has no Wikidata QID, or whose QID matches no stored team
- **WHEN** verification runs
- **THEN** that team's matches are not compared and keep or receive no status
- **AND** a warning naming the team is logged

### Requirement: Verification in the API

Match responses SHALL include `verification`: `null` when the match has no status, otherwise an object with `status`, `reference` (`wikipedia`) and `checked_at` (UTC). `/v1/matches` SHALL accept a `verification` filter taking one status.

#### Scenario: Verified match

- **WHEN** a client GETs a match whose status is `VERIFIED`
- **THEN** `verification` is `{"status": "VERIFIED", "reference": "wikipedia", "checked_at": "<UTC timestamp>"}`

#### Scenario: Competition without verification

- **WHEN** a client GETs a UEFA Champions League match
- **THEN** `verification` is `null`

#### Scenario: Listing mismatches

- **WHEN** a client GETs `/v1/matches?verification=MISMATCH`
- **THEN** only matches whose status is `MISMATCH` are returned

#### Scenario: Unknown status filter

- **WHEN** a client GETs `/v1/matches?verification=MAYBE`
- **THEN** the API responds 422 with the standard error envelope
