# Proposal

## Why

The REST API answers one resource per request: a client that wants a season's matches with both teams, the venue and the verification status pieces it together from several calls, or receives more than it needs. GraphQL lets the client ask for exactly the fields and relations it wants in one request. The data is read-only and already relational (competition → seasons → matches → teams, events), so it fits a graph well.

## What Changes

- **New endpoint `/graphql`**, next to `/v1`, served by the same application. Queries only: the schema has no mutations and no subscriptions.
- **Full parity with REST:** every resource, field, filter and embedded relation `/v1` serves is reachable through GraphQL: competitions, seasons (with coverage), standings (with `asOf`), teams (with seasons), players (with squad coverage), venues and matches (with scorers, line-ups, substitutions, cards, `verification` and `eventsVerification`). The same filters apply, with the same meaning.
- **Graph-native shape:** besides top-level lookups and filtered lists, objects link to each other (a competition to its seasons, a season to its matches and standings, a match to its teams, venue and events, a team to its seasons and players), so a client walks the graph instead of joining IDs.
- **Relay-style connections** for every list (`edges`, `node`, `pageInfo { hasNextPage endCursor }`, `first`, `after`), with the same opaque keyset cursors and page sizes as REST (default 50, at most 200).
- **Abuse limits in the application:** a maximum query depth, a maximum query cost, at most 200 items per list and a limit on aliases. Queries over a limit are refused before running, with a GraphQL error naming the limit. These are needed because the API has no authentication and a proxy's per-request rate limit can't see what one GraphQL request costs.
- **Explorable schema:** introspection is on, and a browser opening `/graphql` gets the GraphiQL explorer, as `/docs` does for REST.
- **REST is unchanged.** Both APIs read through the same query and filter code, so they can't drift apart.
- New dependency: `strawberry-graphql`.

## Capabilities

### New Capabilities

- `graphql-api`: the GraphQL endpoint: its schema and its parity with the REST resources, connections and cursors, errors, abuse limits, batching of related lookups, and the explorer.

### Modified Capabilities

None. The REST contracts in `catalog`, `matches`, `match-events`, `standings` and `match-verification` stay as they are; `graphql-api` refers to them for what each field means.

## Impact

- **Code:** a new `football_api.api.graphql` package (schema types, resolvers, DataLoaders, limits), mounted in `api/app.py`. The query and filter logic now in `api/v1.py` moves into functions both APIs call; REST responses don't change.
- **Dependencies:** `strawberry-graphql` (with its FastAPI integration).
- **API:** additive. A new `/graphql` path; nothing removed or renamed under `/v1`.
- **Tests:** schema snapshot, parity tests against REST for every resource and filter, limit tests, and a query-count test for batching.
- **Docs:** README (GraphQL section and an example query) and the app description.
- **Deployment:** a reverse proxy in front of a public instance must also route `/graphql`; its rate limit stays as it is.
