# Spec Delta

## MODIFIED Requirements

### Requirement: Query limits

A query SHALL be refused before it runs, with an error naming the limit in `extensions.code` and the measured and allowed values in `extensions`, when its depth exceeds 10 (`query_too_deep`) or it uses more than 20 aliases (`too_many_aliases`). Depth SHALL count each level of selected fields, except a connection's `edges` and an edge's `node`, which add none. Introspection queries SHALL be exempt from the depth limit.

#### Scenario: Too deep

- **WHEN** a client sends a query nesting 11 levels of selections, none of them `edges` or `node`
- **THEN** it is refused with `query_too_deep`, the measured depth and the limit 10, and nothing is read from the database

#### Scenario: Connections don't add depth

- **WHEN** a client queries `competitions(first: 5) { edges { node { seasons(first: 5) { edges { node { matches(first: 5) { edges { node { homeTeam { name } } } } } } } } } }`
- **THEN** its depth is 5 and the query runs

#### Scenario: Alias flood

- **WHEN** a client sends 21 aliased copies of `match(id:)` in one query
- **THEN** it is refused with `too_many_aliases`

#### Scenario: Schema introspection

- **WHEN** a client sends the standard introspection query used by GraphQL tools
- **THEN** it gets the schema
