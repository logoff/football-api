# Design

## Context

`api/graphql/limits.py` walks each operation once and adds a level for every field it descends into. Connections are `XConnection { edges: [XEdge] }` and `XEdge { node: X }` (and `PlayerConnection` / `PlayerEdge`), so each list adds two levels before reaching its objects.

## Goals / Non-Goals

**Goals:** depth measures hops between objects; the limit still bounds cyclic walks (season → competition → seasons → …).

**Non-Goals:** changing the limit's value, the cost model or the alias limit.

## Decisions

### D1. Skip the wrappers by type and field

A field adds no depth when it is `edges` on a type whose name ends in `Connection`, or `node` on a type whose name ends in `Edge`. Every connection in the schema follows that naming (the committed `schema.graphql` shows them), and a new one built with the generic `Connection[T]` gets it automatically.

- **Alternative:** a marker on each connection type. More machinery for the same result while the naming holds.
- `pageInfo` keeps counting: it holds scalars only, so it never deepens a query by more than its own two levels.

### D2. Recursion stays bounded

The walk stops descending past `MAX_DEPTH + 1` levels. Wrappers don't add levels, but they can't nest without an object between them (`edges → node → object`), so the recursion is still at most about three times the limit.

## Risks / Trade-offs

- **\[A future type named `…Connection` that isn't a connection\]** → its `edges` field would add no depth. Unlikely; the naming is the schema's convention.
