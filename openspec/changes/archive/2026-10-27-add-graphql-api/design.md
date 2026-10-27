# Design

## Context

The REST API (`api/v1.py`, ~600 lines) builds SQLAlchemy selects inline in each endpoint, pages them with `apply_keyset`/`page_cursor` (`api/pagination.py`), converts rows to Pydantic `*Out` models (`api/schemas.py`) and embeds relations on `?expand=`. Sessions come from `infra/db.py` (async SQLAlchemy, asyncpg). There is no authentication; public instances sit behind a reverse proxy with a per-client rate limit. See proposal.md for why GraphQL, and `specs/graphql-api/spec.md` for the behavior.

## Goals / Non-Goals

**Goals:**

- One query layer behind both APIs, so filters, ordering and derived values (coverage, verification, formations, standings) are computed once.
- A request's cost is known and capped before any SQL runs.
- A query's number of SQL statements doesn't grow with the number of objects it returns.

**Non-Goals:**

- Mutations, subscriptions, persisted queries, `@defer`/`@stream`.
- Relay's global object identification (`Node`, `node(id:)`): IDs stay plain UUIDs.
- Per-client quotas or API keys: that's the future gateway change.
- Response caching.

## Decisions

### D1. Strawberry, code-first

`strawberry-graphql[fastapi]` with its `GraphQLRouter` mounted at `/graphql` in `create_app()`.

- **Why:** typed Python classes fit pyright strict and the existing style; async resolvers and a DataLoader come built in; the router serves GraphiQL and handles `GET`/`POST`.
- **Alternatives:** Ariadne (schema-first SDL plus untyped resolvers: two sources of truth, weaker typing); Graphene (older API, weaker async and typing story).

### D2. A shared query layer, extracted from `v1.py`

A new `football_api.api.queries` module holds, per resource, a function that takes a session and typed filters and returns ORM rows (lists through `apply_keyset`, so REST and GraphQL page identically), plus the derived-value helpers now private to `v1.py` (`_season_out` coverage, match verification and coverage, line-up grouping and formation, standings computation). `v1.py` keeps its routes and Pydantic models but calls these functions; GraphQL resolvers call the same ones.

- **Why:** parity by construction. A new filter or a fix lands in one place.
- **Alternative:** GraphQL resolvers calling the REST endpoint functions (couples GraphQL to FastAPI `Query` defaults and to `expand` strings); or separate GraphQL queries (drift).
- REST output is guarded by the existing `tests/test_api.py`; the refactor lands first, with those tests unchanged.

### D3. GraphQL types are Strawberry classes built from ORM rows, not generated from Pydantic

Each type (`Competition`, `Season`, `Match`, …) is a `@strawberry.type` with scalar fields filled from the ORM row and relation fields as resolvers. Values that REST derives go through the shared helpers from D2.

- **Why:** Strawberry's Pydantic integration is experimental, and the REST models embed relations eagerly by `expand`, while GraphQL needs lazy per-field resolution.
- **Guard:** parity tests (D9) compare REST and GraphQL values for every resource.

### D4. Connections: hand-rolled, on the existing cursors

A generic `Connection[T]` with `edges { cursor node }` and `pageInfo { hasNextPage endCursor }`. `first` defaults to 50 and is capped at 200 (`DEFAULT_LIMIT`, `MAX_LIMIT`); `after` is the REST cursor string. The edge cursor is the same base64url JSON of the row's sort key that REST puts in `next_cursor`.

- **Why:** reuses keyset pagination exactly, keeps UUIDs as the only IDs.
- **Alternative:** `strawberry.relay`, rejected because it introduces base64 global IDs and the `Node` interface.
- Nested connections (a season's matches, a competition's seasons) use the same function with the parent's filter applied. They aren't batched across parents (see Risks).

### D5. DataLoaders per request

A context object per request holds the `AsyncSession` and one DataLoader per to-one or small to-many relation: team, venue, season, competition, player by ID; goals, line-up entries, substitutions and cards by match ID; team-seasons by team ID. A loader issues one `WHERE id IN (…)` select per batch.

- **Why:** the Batched lookups requirement; the REST code already batches events per page the same way (`_events_by_match`).
- One session per request, opened by the router's `context_getter` from `session_dependency`.

### D6. Limits as validation rules, checked before execution

| Limit     | Value         | Mechanism                                                                |
| --------- | ------------- | ------------------------------------------------------------------------ |
| Depth     | 10            | Strawberry `QueryDepthLimiter` (ignores introspection fields by default) |
| Aliases   | 20            | Strawberry `MaxAliasesLimiter`                                           |
| Page size | `first` ≤ 200 | Validation rule over literal and variable `first` arguments              |
| Cost      | 50,000        | Custom validation rule (below)                                           |

**Cost model.** Walk the operation (with variables and fragments resolved): a scalar costs 0; an object field costs 1 plus its selection; a connection costs `first` (or 50) × (1 + its selection); a plain list with a known bound counts a fixed size × (1 + its selection): line-up side 25, goals 10, substitutions 12, cards 12, a team's seasons 40, standings tables 12, table rows 24, row adjustments 2.

50,000 is chosen so the largest REST request stays possible: 200 matches with teams, venue, scorers, line-ups, substitutions and cards, each event with its player, cost about 200 × 192 ≈ 38,400 (a REST page of that size returns about as many objects). The scenario's 200 × 200 × 200 matches costs millions. (The first draft said 25,000 from an estimate that left out the player on each event; the tests measure the real figure.)

Each refusal raises a `GraphQLError` with `extensions` `{code, measured, limit}` and happens in validation, so nothing touches the database.

- **Alternative:** a timeout per request only (still lets one request hold a connection for its duration); or rate limiting by response size (costs are known only after the work is done).

### D7. Errors

`ApiError` codes map to `extensions.code` (`invalid_cursor`, …). A lookup of an unknown UUID returns `null` (GraphQL convention; REST's 404 has no per-field equivalent). Unexpected exceptions are masked to `internal_error` with Strawberry's `MaskErrors`, and logged.

### D8. Queries only; introspection and GraphiQL on

The schema has a `Query` type only, so graphql-core refuses mutations and subscriptions in validation. `graphql_ide="graphiql"` serves the explorer to browsers. `allow_queries_via_get=True` (read-only, so no CSRF concern).

### D9. Committed SDL and parity tests

- `schema.graphql` is exported with `strawberry export-schema` (a `just graphql-schema` recipe) and committed. A test fails when the live schema differs, so any schema change shows up in the PR diff.
- Parity tests run the same request through REST and GraphQL for every resource and filter against the test database and compare values after mapping field names.
- A query-count test counts SQL statements (SQLAlchemy `before_cursor_execute` event) for 2 and for 200 matches with the same selection.

## Risks / Trade-offs

- **[Nested connections are not batched across parents]** → `competitions { seasons { matches } }` runs one paged select per parent. The cost limit caps the number of parents (the outer `first`), so the statement count stays bounded by the cost. Batching windowed pages (`ROW_NUMBER() OVER (PARTITION BY …)`) can come later if real traffic needs it.
- **[Cost model drifts from the real expense]** → it's a static estimate. Keep the weights next to the types they describe, and revisit if the query-count or timing tests show a hot spot.
- **[The D2 refactor could change REST output]** → land it as the first task, with `tests/test_api.py` unchanged and passing, before any GraphQL code.
- **[GraphiQL loads its assets from a CDN]** → acceptable for a public read-only API, like FastAPI's `/docs`. If self-hosting is wanted later, Strawberry can serve a local copy.
- **[Proxy rate limits count requests, not cost]** → one GraphQL request can do up to 50,000 units of work. D6 caps it; the proxy's concurrency cap still applies.

## Migration Plan

Additive. Deploy as usual: the image gains `/graphql`. A reverse proxy that routes only `/v1` and `/docs` must also route `/graphql`. Rollback: deploy the previous image; nothing in the database changes.
