# Tasks

## 1. Depth by objects

- [x] 1.1 Skip `edges` on `…Connection` types and `node` on `…Edge` types in the depth walk (D1). Verify with tests: the spec's competitions → seasons → matches → homeTeam query runs; a query 11 levels deep without wrappers is refused with `query_too_deep`, measured 11, and no SQL; a cyclic walk season → competition → seasons → … past 10 objects is refused.
- [x] 1.2 Update the README's limits paragraph. Verify that the README examples test still passes.
- [x] 1.3 Verify that `just typecheck`, `just test` and `openspec validate graphql-depth-by-objects --strict` pass.

## Workflow follow-up

- Archive this change once it's merged.
