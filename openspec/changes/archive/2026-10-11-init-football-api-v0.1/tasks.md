# Init Football API v0.1 — Tasks

## 1. Project foundation

- [x] 1.1 Initialize the project with `uv init` (Python 3.12).
- [x] 1.2 Add core dependencies: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic`, `pydantic-settings`, `httpx`, `pytest`, `pytest-asyncio`, `pyright`.
- [x] 1.3 Configure pyright in **strict** mode (`pyrightconfig.json`).
- [x] 1.4 Lay out package structure: `src/football_api/{api,ingestion,domain,infra}` with `__init__.py` in each.
- [x] 1.5 Add `.env.example` and a `Settings` class via `pydantic-settings`.
- [x] 1.6 Add `justfile` with recipe stubs for `install`, `up`, `down`, `sync`, `test`, `typecheck`. Document `just` as a required system-wide tool in the README.

## 2. Database schema

- [x] 2.1 Author SQLAlchemy 2.0 `Mapped[]`-style models for all entities in `design.md`.
- [x] 2.2 Set up Alembic; generate the initial migration.
- [x] 2.3 Add unique indexes on `external_ref(entity_type, source, source_id)`, `match(season_id, stage, home_team_id, away_team_id)`, and `goal(match_id, ordinal)`.
- [x] 2.4 Seed `competition` rows for the 13 in-scope competitions.

## 3. Ingestion — Wikidata seed

- [x] 3.1 Write `seeds/teams.yaml` for every team in the 13 in-scope competitions (clubs incl. non-top-5 qualifiers like Benfica, Al Hilal, Auckland City; national teams of the 3 nations cups): name, kind, country, Wikidata QID, Open Football aliases.
- [x] 3.2 Seed loader: match `team` rows through their `external_ref` rows (aliases, QID), create missing ones, and write `external_ref` rows for each QID and alias.
- [x] 3.3 SPARQL enrichment for the seeded QIDs and competition QIDs; idempotent via `external_ref(source=wikidata, source_id)`.
- [x] 3.4 Graceful handling when SPARQL endpoint is unavailable (log + skip).

## 4. Ingestion — Open Football

- [x] 4.1 Parser for the openfootball text DSL (matchday headers, date markers, match lines, comments).
- [x] 4.2 JSON mirror reader (preferred when present and current).
- [x] 4.3 Team-name resolver via `external_ref(source=openfootball)` aliases from `seeds/teams.yaml`; fail loudly on unknown names.
- [x] 4.4 Per-source-file time-zone config (hand-verified per file); parser honours explicit `UTC±N` offsets on match lines first.
- [x] 4.5 Score parser for `a.e.t.` and `pen.` notations → `home/away_score`, `decided_by`, `home/away_pens`.
- [x] 4.6 Match upsert by `(season_id, stage, home_team_id, away_team_id)`; set `original_kickoff_utc` on first observed kickoff change.
- [x] 4.7 Squad-file parser → players keyed by `(team, season, display_name)` for WC 2022, Euro 2024, Copa América 2024, Club World Cup 2025. For Club World Cup, split on the capitalised surname and title-case all stored names; fully capitalised names → display only.
- [x] 4.8 Goal extraction (WC, Euro, Copa América, Club World Cup `-full` file): parse minutes as `minute` + `added_minute`; upsert by `(match_id, ordinal)`, resolve scorer to squad member (case- and accent-insensitive) or keep `scorer_name`; delete surplus ordinals.
- [x] 4.9 Venue extraction from `@ Stadium, City` match-line suffixes, keyed by `(name, city)`.
- [x] 4.10 `just sync` recipe that orchestrates team seed, Wikidata enrichment, then Open Football load.

## 5. REST API

- [x] 5.1 FastAPI app skeleton; `/v1` router; root health endpoint `GET /healthz`.
- [x] 5.2 `GET /v1/competitions` and `GET /v1/competitions/{id}`.
- [x] 5.3 `GET /v1/seasons` (filterable by `competition_id`).
- [x] 5.4 `GET /v1/teams` (filterable by `competition_id`, `season_id`, `kind`) and `GET /v1/teams/{id}` (with `?expand=seasons`).
- [x] 5.5 `GET /v1/players` and `GET /v1/players/{id}`.
- [x] 5.6 `GET /v1/matches` (filterable by `competition_id`, `season_id`, `team_id`, stage, date range; `?expand=teams,scorers,venue`).
- [x] 5.7 `GET /v1/matches/{id}` and `GET /v1/venues/{id}`. All path IDs validated as UUIDs (422 otherwise).
- [x] 5.8 Cursor-based pagination helper shared across list endpoints.
- [x] 5.9 Error envelope + global exception handlers.
- [x] 5.10 OpenAPI metadata polish (descriptions, examples, tags).

## 6. Tests

- [x] 6.1 Unit tests for the Open Football parser (golden-file fixtures).
- [x] 6.2 Ingestion idempotency tests (run sync twice; assert byte-equal entity state).
- [x] 6.3 API smoke tests for each endpoint with httpx TestClient against a seeded test DB.

## 7. Deployment

- [x] 7.1 `Dockerfile` (multi-stage: uv install layer, slim runtime).
- [x] 7.2 `docker-compose.yml` (api bound to `127.0.0.1:8000`; postgres with named volume).
- [x] 7.3 `just up`, `just down`, `just logs` recipes.
- [x] 7.4 `README.md` with one-command quickstart and explicit "Security posture" section.

## 8. Definition of done

- [x] 8.1 `just up && just sync` produces a populated DB on a clean machine.
- [x] 8.2 `curl localhost:8000/v1/competitions` returns all 13 in-scope competitions.
- [x] 8.3 OpenAPI docs render at `/docs` with examples for each endpoint.
- [x] 8.4 README documents per-competition coverage (scorers and squads: full for WC, Euro, Copa América, Club World Cup; none elsewhere) and the deferred competitions (AFCON, Sudamericana, Intercontinental Cup).
- [x] 8.5 `just typecheck` and `just test` pass cleanly.
