# Proposal

## Why

The GraphQL depth limit counts every selection set, so each list costs two extra levels for its `edges { node { … } }` wrapper. A natural query such as `competitions → seasons → matches → homeTeam { name }` is 11 levels deep and refused, although it reads only four kinds of object. The limit should measure how far a query walks the graph, not how the connections are spelled.

## What Changes

- A connection's `edges` and an edge's `node` no longer count toward a query's depth. Every other selection still counts one level. The limit stays at 10.
- `competitions → seasons → matches → homeTeam { name }` now measures 5 and runs. A query that walks 11 objects deep (for example season → competition → seasons → competition → …) is still refused with `query_too_deep`.
- The cost limit is unchanged: it already counts every object a list can return.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graphql-api`: Query limits. Depth counts the levels of objects and fields, not a connection's `edges` and `node` wrappers.

## Impact

- **Code:** `api/graphql/limits.py` (the depth walk).
- **API:** queries refused today for depth alone may run; nothing that runs today is refused.
- **Tests and docs:** the depth tests in `tests/test_graphql.py`; the README's limits paragraph.
