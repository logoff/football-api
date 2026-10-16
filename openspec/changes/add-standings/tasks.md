# Tasks

## 1. Rules and seeds

- [x] 1.1 Seed models: a `standings` block per competition (eras: `from`, points, tie-breakers; per-season `ranking`) and `seeds/standings.yaml` (point adjustments, orders), validated at load against competitions, seasons and teams. Verify with seed tests: valid entries load; an unknown team, season or criterion fails.
- [x] 1.2 Ranking rules for every competition from its regulations (leagues, UEFA group stage and league phase, World Cup, Euro, Copa América, Copa Libertadores, Club World Cup). Verify that each era cites the regulation in a comment.
- [x] 1.3 Initial adjustments: the known point deductions in the seasons held, each with an official source. Verify that the seeds load.

## 2. Computation

- [x] 2.1 Grouping (D3): phases, named groups, connected components for unnamed ones. Verify with unit tests: the label spellings, the World Cup second round, and an unnamed group stage.
- [x] 2.2 Ranking (D4): points or points per game, each criterion, head-to-head among the tied subset, `h2h_reapply`, `tied`. Verify with unit tests built from small hand-made results, one per criterion and per scenario in the spec.
- [x] 2.3 Adjustments and status (D5, D6), and `as_of`. Verify with unit tests.

## 3. API

- [x] 3.1 `GET /v1/seasons/{id}/standings` with `as_of` and `expand=teams`, plus schemas and OpenAPI docs. Verify with API tests on the fixture database: a league season, a tournament with groups, 404, a season without table matches.

## 4. Docs and integration

- [x] 4.1 README: the endpoint and the seeds. Verify that mdformat leaves no changes.
- [x] 4.2 On a full local database, spot-check final tables against official tables: Premier League 2023-24 (with deductions), La Liga 2023-24, Bundesliga 2023-24, Serie A 2022-23, Ligue 1 2019-20 (points per game), World Cup 2022 and 1982, Champions League 2023-24 (unnamed groups) and 2024-25 (league phase). Record the outcome in the PR.
- [x] 4.3 Verify that `just typecheck`, `just test` and `openspec validate add-standings --strict` all pass.

## Workflow follow-up

- `verify-standings`: compare final tables with Wikipedia's standings.
- Archive this change once it's merged.
