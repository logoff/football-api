# Spec Delta

## ADDED Requirements

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
