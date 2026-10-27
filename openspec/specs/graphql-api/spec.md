# graphql-api Specification

## Purpose

Serve the same read-only football data as the REST API through a GraphQL endpoint, so clients can fetch exactly the fields and related objects they need in one request, within limits that keep any single request affordable.

## Requirements

### Requirement: GraphQL endpoint

The system SHALL serve GraphQL at `/graphql`, accepting queries by `POST` with a JSON body and by `GET` with query parameters. The schema SHALL define queries only. An operation that is a mutation or a subscription SHALL be refused with an error.

#### Scenario: Query by POST

- **WHEN** a client POSTs `{"query": "{ competitions(first: 2) { edges { node { name } } } }"}` to `/graphql`
- **THEN** the response is HTTP 200 with `data.competitions.edges` holding two competitions' names

#### Scenario: Mutation refused

- **WHEN** a client POSTs an operation starting with `mutation`
- **THEN** the response has an error and no `data` for it

### Requirement: Parity with REST

Every resource, field and embedded relation the REST API serves under `/v1` SHALL be available through GraphQL with the same values: competitions, seasons with their coverage, standings, teams with their seasons, players with squad coverage, venues, and matches with scorers, line-ups, formations, substitutions, cards, referee, attendance, `verification` and `eventsVerification`. Field names SHALL be camelCase; enum values, UUIDs and UTC timestamps SHALL be written as in REST.

#### Scenario: Same match through both APIs

- **GIVEN** a World Cup match with line-ups, cards and a `VERIFIED` result
- **WHEN** a client GETs `/v1/matches/{id}?expand=teams,venue,scorers,lineups,substitutions,cards` and queries `match(id:)` for the same fields
- **THEN** every value is the same in both responses, apart from the field-name casing

#### Scenario: Season coverage

- **WHEN** a client queries a Champions League season's `coverage`
- **THEN** `lineups`, `substitutions` and `cards` are `none`, as in REST

### Requirement: Top-level queries

The schema SHALL offer a lookup by UUID for each resource (`competition`, `season`, `team`, `player`, `venue`, `match`) and a list for each REST list endpoint, taking the same filters with the same meaning: `competitions(format)`, `seasons(competitionId)`, `teams(competitionId, seasonId, kind)`, `players(teamId, seasonId, competitionId)`, `venues`, and `matches(competitionId, seasonId, teamId, stage, from, to, verification, eventsVerification)`. A lookup of an unknown UUID SHALL return `null`.

#### Scenario: Filtered matches

- **WHEN** a client queries `matches(seasonId: <La Liga 2024-25>, verification: MISMATCH)`
- **THEN** it gets the same matches, in the same order, as `/v1/matches?season_id=…&verification=MISMATCH`

#### Scenario: Unknown match

- **WHEN** a client queries `match(id: "<a UUID that matches nothing>")`
- **THEN** `data.match` is `null` and there is no error

### Requirement: Related objects

Objects SHALL link to their related objects instead of only carrying their UUIDs: a competition to its seasons; a season to its competition, teams, matches and standings (taking `asOf`); a match to its season, home and away teams, venue, scorers, line-ups, substitutions and cards; a team to its seasons and players; a player, goal, line-up entry, substitution or card to its player when the REST response names one.

#### Scenario: From a competition down to the events

- **WHEN** a client queries `competition(id:) { seasons(first: 1) { edges { node { matches(first: 5) { edges { node { homeTeam { name } cards { kind player { displayName } } } } } } } } }`
- **THEN** it gets each match's home team and cards in one response, with the values the REST endpoints serve

#### Scenario: Standings as of a date

- **WHEN** a client queries a season's `standings(asOf: "2025-01-01")`
- **THEN** the tables are the ones `/v1/seasons/{id}/standings?as_of=2025-01-01` serves

### Requirement: Connections

Every list SHALL be a connection with `edges { cursor node }` and `pageInfo { hasNextPage endCursor }`, taking `first` (default 50, at most 200) and `after`. Lists SHALL keep the order REST uses, and paging with `after: endCursor` SHALL return the next items with none repeated or skipped, as REST cursors do.

#### Scenario: Next page

- **GIVEN** a season with 380 matches
- **WHEN** a client queries `matches(seasonId:, first: 200)` and then `matches(seasonId:, first: 200, after: <endCursor>)`
- **THEN** the two pages hold the 380 matches once each, and the second has `hasNextPage: false`

#### Scenario: Page too large

- **WHEN** a client asks for `first: 500`
- **THEN** the query is refused before running, with an error whose `extensions.code` is `page_too_large`

### Requirement: Errors

Errors SHALL follow the GraphQL response format, each with a `message` and an `extensions.code`. Input errors SHALL use the same codes as REST where REST has one (for example `invalid_cursor`). An error inside one field SHALL leave the rest of the response's data in place.

#### Scenario: Bad cursor

- **WHEN** a client passes `after: "not-a-cursor"`
- **THEN** the response has an error with `extensions.code` `invalid_cursor` on that list

### Requirement: Query limits

A query SHALL be refused before it runs, with an error naming the limit in `extensions.code` and the measured and allowed values in `extensions`, when its depth exceeds 10 (`query_too_deep`) or it uses more than 20 aliases (`too_many_aliases`). Introspection queries SHALL be exempt from the depth limit.

#### Scenario: Too deep

- **WHEN** a client sends a query nesting 11 levels of selections
- **THEN** it is refused with `query_too_deep`, the measured depth and the limit 10, and nothing is read from the database

#### Scenario: Alias flood

- **WHEN** a client sends 21 aliased copies of `match(id:)` in one query
- **THEN** it is refused with `too_many_aliases`

#### Scenario: Schema introspection

- **WHEN** a client sends the standard introspection query used by GraphQL tools
- **THEN** it gets the schema

### Requirement: Query cost

A query whose cost exceeds the allowed cost SHALL be refused before it runs with `query_too_costly`, the computed cost and the allowed cost. The cost SHALL grow with the number of objects a query can return: each list counts its `first` (or the default) times the cost of what is selected inside it. The allowed cost SHALL be documented and SHALL admit the largest request REST serves: 200 matches with every embedded relation.

#### Scenario: Too costly

- **WHEN** a client asks for 200 competitions, each with 200 seasons, each with 200 matches, within the depth limit
- **THEN** it is refused with `query_too_costly`, the computed cost and the allowed cost

#### Scenario: Largest REST page

- **WHEN** a client asks for 200 matches with teams, venue, scorers, line-ups, substitutions and cards
- **THEN** the query runs

### Requirement: Batched lookups

Resolving the same relation for many objects in one query SHALL read the database a bounded number of times, independent of how many objects the query returns.

#### Scenario: Teams of many matches

- **WHEN** a client queries 200 matches with `homeTeam`, `awayTeam` and `venue`
- **THEN** the number of database queries is the same as for 2 matches with those fields

### Requirement: Explorer

A browser that opens `/graphql` (a `GET` asking for HTML without a query) SHALL get an interactive explorer for writing and running queries against the schema.

#### Scenario: Opening the endpoint in a browser

- **WHEN** a browser GETs `/graphql` with `Accept: text/html`
- **THEN** the response is an HTML page with the GraphQL explorer
