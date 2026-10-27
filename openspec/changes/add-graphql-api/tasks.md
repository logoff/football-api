# Tasks

## 1. Shared query layer

- [x] 1.1 Move the per-resource selects, filters and keyset paging out of `api/v1.py` into `football_api.api.queries` (D2), with `v1.py` calling them. Verify that `tests/test_api.py` passes unchanged and `just typecheck` is clean.
- [x] 1.2 Move the derived-value helpers (season coverage, match coverage and verification, line-up grouping and formation, events batching, standings) into the shared layer. Verify with `tests/test_api.py` and `tests/test_standings.py` unchanged.

## 2. Schema and endpoint

- [x] 2.1 Add `strawberry-graphql[fastapi]`, mount `GraphQLRouter` at `/graphql` with a per-request context (session, loaders), queries only, GraphiQL and GET queries on (D1, D5, D8). Verify with tests: a `POST` and a `GET` query answer, a mutation is refused, a browser `GET` with `Accept: text/html` returns the explorer.
- [x] 2.2 Add the generic connection type over `apply_keyset`/`page_cursor` (D4). Verify with tests: default and maximum `first`, paging a 380-match season in two pages with none repeated or skipped, and `invalid_cursor` on a bad `after`.
- [x] 2.3 Add the catalog types and top-level queries: competitions, seasons with coverage, teams with seasons, players with squad coverage, venues, each lookup returning `null` for an unknown UUID (D3, D7). Verify with parity tests against the matching REST responses for every filter.
- [x] 2.4 Add matches with every REST filter, scorers, line-ups, formations, substitutions, cards, referee, attendance, `verification` and `eventsVerification`. Verify with parity tests against `/v1/matches` and `/v1/matches/{id}` with every `expand`, including a season without events coverage.
- [x] 2.5 Add standings on seasons, taking `asOf`, with team links and row verification. Verify with parity tests against `/v1/seasons/{id}/standings` with and without `as_of`.
- [x] 2.6 Add the graph links between types (competition → seasons, season → competition, teams, matches, standings; match → season, teams, venue; team → seasons, players; event → player). Verify with a test walking from a competition down to a match's cards, compared with the REST values.
- [x] 2.7 Add the DataLoaders for every to-one and per-match relation (D5). Verify with the query-count test: 2 and 200 matches with teams, venue and events run the same number of SQL statements.

## 3. Limits

- [ ] 3.1 Add the depth (10) and alias (20) limits and the `first` ≤ 200 rule, each refusing with `extensions` `code`, `measured` and `limit` (D6). Verify with a test per spec scenario, including that the standard introspection query still works and that a refused query issues no SQL.
- [ ] 3.2 Add the cost rule with the weights and the 25,000 limit (D6). Verify with tests: the 200 × 200 × 200 query is refused with `query_too_costly`; 200 matches with every relation (the largest REST request) is allowed; fragments and variables are counted.

## 4. Schema file and docs

- [ ] 4.1 Add a `just graphql-schema` recipe exporting `schema.graphql`, commit the file, and add a test that fails when the live schema differs (D9). Verify by changing a field locally and seeing the test fail.
- [ ] 4.2 Document GraphQL in the README (endpoint, an example query, connections, the limits and the cost model) and in the app description. Format the README with mdformat. Verify by running the README's example query against a local `just up && just sync`.
- [ ] 4.3 Verify that `just typecheck`, `just test` and `openspec validate add-graphql-api --strict` pass.

## Workflow follow-up

- Deployment: make sure the reverse proxy routes `/graphql` on public instances (outside this repo).
- Archive this change once it's merged.
