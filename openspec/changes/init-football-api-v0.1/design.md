# Init Football API v0.1 — Design

## Context

This is the bootstrap change for the project. There is no existing code or schema. All architectural decisions in this document set the foundation for subsequent changes.

Defining constraints:

- Solo developer, optimizing for velocity and "still-working-on-it-in-six-months" odds.
- Data sources are public-domain (CC0) text/JSON files in git repositories, supplemented by Wikidata for canonical entity identifiers.
- Target deployment is a single Docker Compose stack on a self-hosted VPS.
- API consumers will eventually be served behind an API gateway; auth and rate-limiting happen there, not in app code.

## Stack

| Concern          | Choice                           | Rationale                                                                                                                 |
| ---------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Language         | Python 3.12                      | Fastest path to MVP for solo dev; best scraping ergonomics for Phase 2                                                    |
| Package manager  | **uv**                           | Fast, reproducible; replaces pip + venv + pyenv                                                                           |
| Web framework    | FastAPI                          | First-class OpenAPI, async, Pydantic-native                                                                               |
| Type checker     | pyright (strict)                 | Recovers most of the safety of a static language                                                                          |
| ORM / DB toolkit | SQLAlchemy 2.0 (async, Mapped[]) | Mature, type-friendly                                                                                                     |
| DB driver        | asyncpg                          | Performance + async                                                                                                       |
| Database         | PostgreSQL 18 (pinned `18.4`)    | Production-grade; native `uuidv7()` removes need for app-side UUID generation; built-in AIO benefits read-heavy workloads |
| Migrations       | Alembic                          | Standard SQLAlchemy migration tool                                                                                        |
| Validation       | Pydantic v2                      | Already in FastAPI; reuse for ingestion DTOs                                                                              |
| HTTP client      | httpx                            | Async; used for Wikidata SPARQL                                                                                           |
| Tests            | pytest + httpx TestClient        | Standard                                                                                                                  |
| Container        | Docker + Compose                 | Smallest viable deployment artifact                                                                                       |

## Domain model

Conceptual schema — full DDL lives in the Alembic migration produced under tasks 2.x.

- **competition** — `id (uuid, default uuidv7())`, `name`, `country (ISO 3166-1 alpha-2, or ISO 3166-2 for the UK home nations — GB-ENG, GB-SCT, GB-WLS, GB-NIR; nullable for international competitions)`, `team_kind (CLUB | NATIONAL)`, `scope (DOMESTIC | CONTINENTAL | INTERCONTINENTAL)`
- **season** — `id`, `competition_id`, `label ("2024-25" | "2022")`, `starts_on`, `ends_on`, `status (SCHEDULED | IN_PROGRESS | COMPLETED)`, `scorers_coverage (full | none)`, `players_coverage (full | none)` — coverage is stored per season so the API never reads seed files at runtime
- **team** — `id`, `name`, `country`, `kind (CLUB | NATIONAL)`
- **team_season** — many-to-many between team and season
- **venue** — `id`, `name`, `city`, `country`
- **player** — `id`, `display_name` (source text; case-normalised for capitalised-surname sources), `full_name (nullable)`, `given_name (nullable)`, `family_name (nullable)`, `birth_year (nullable)`, `dob (nullable)`, `nationality (nullable)`, `position (nullable)`
- **player_team_season** — squad membership per season
- **match** — `id`, `season_id`, `home_team_id`, `away_team_id`, `venue_id (nullable)`, `kickoff_utc`, `original_kickoff_utc (nullable)`, `status (SCHEDULED | COMPLETED | CANCELLED | POSTPONED)`, `home_score (nullable)`, `away_score (nullable)`, `decided_by (REGULAR | EXTRA_TIME | PENALTIES, nullable)`, `home_pens (nullable)`, `away_pens (nullable)`, `stage (QUALIFYING | LEAGUE | GROUP | PLAYOFF | R32 | R16 | QF | SF | THIRD_PLACE | FINAL)`, `matchday (nullable)`, `round_label` (source text, e.g. `First stage / Group A`)
- **goal** — `id`, `match_id`, `ordinal` (1-based position within the match, in source order), `scorer_player_id (nullable)`, `scorer_name (nullable; raw source text, kept when no player match)`, `minute (nullable)`, `added_minute (nullable; `90+5'` → minute 90, added 5)`, `is_own_goal`, `is_penalty`, `side (HOME | AWAY)`
- **external_ref** — `(entity_type, entity_id, source, source_id)`, unique on `(entity_type, source, source_id)` — the single source-agnostic mapping from a canonical entity UUID to its identifier in any external system. The entity type is part of the key because openfootball identifiers are names, and a team and a venue may share one.

All other entity tables (`season`, `team`, `venue`, `player`, `match`, `goal`, `external_ref`) follow the same pattern: a `uuid` primary key with `DEFAULT uuidv7()`.

### ID principles

1. **Internal UUIDs are the only canonical identifiers.** Every entity row gets a server-generated UUID v7 at creation (via PG 18's native `uuidv7()`); that UUID never changes. UUID v7 is timestamp-ordered, giving better B-tree insert locality than v4.
1. **No external identifier is stored on entity tables.** All external IDs (Wikidata QID, Open Football name or file path, future API-Football ID, future SportMonks ID, …) live exclusively in `external_ref`. Adding a new source therefore requires zero schema changes — just new `external_ref` rows.
1. **No source is privileged.** `external_ref.source` is just a label (`wikidata`, `openfootball`, etc.); reconciliation logic treats every source symmetrically.
1. **No slugs.** UUIDs are the only identifiers the API accepts or returns, in paths and in filters (`/v1/matches?season_id=…&team_id=…`). Human-readable keys were dropped (2026-10-10): they are a second public identifier to keep stable forever, and every rename becomes a breaking change. Clients find IDs by listing a resource and reading names. Seed entries are matched to rows through their external identifiers (Wikidata QID, Open Football spellings), never through a key we invent.

## Reconciliation decisions

These rules settle how source records map to canonical rows. They were decided in an explore session (2026-10-10) after inspecting the actual openfootball files.

### Teams — curated seed file

Team identity across sources is pinned by hand in `seeds/teams.yaml`, not discovered by name matching:

```yaml
- name: Manchester United
  kind: CLUB
  country: GB
  wikidata: Q18656
  openfootball: ["Manchester United FC", "Man United", "Man Utd"]
```

Sync loads this file first. Each entry is matched to an existing team through its `external_ref` rows (any alias or the QID); otherwise a new team is created. It then writes one `external_ref` per alias and for the QID. An entry whose identifiers point at two existing teams fails the sync, since that is a merge to do by hand. A source team name not present in the file fails the sync (file, line, name). Rationale: automatic name → QID matching silently creates duplicate teams; ~150 hand-checked rows is cheap and deterministic.

### Players — squads first, scorers matched to squads

- Players from national-team squads get `nationality` = their team's country.
- Players are created **only** from squad files (`worldcup/more/2022_squads.txt`, `euro/2024--germany/squads/*`, `copa-america/2024--usa/squads/*`, `club-worldcup/more/2025_clubworldcup-squads.txt`). Natural key: `(team, season, display_name)`.
- Scorer strings (`Koulibaly 70'`) are resolved against that match's two squads by display name, then by unique surname suffix. All name comparisons are case- and accent-insensitive (`Suárez` = `SUAREZ`). If no unique match exists, the goal keeps `scorer_name` and `scorer_player_id = null`. No player row is created from a scorer string.
- Names are never split by guessing. `given_name` / `family_name` are filled only when the source marks the surname itself, or from Wikidata (players are not yet linked to Wikidata in v0.1).
- **Capitalised-surname sources** (`club-worldcup/more/2025_clubworldcup-*.txt`) write the family name in capitals: `Lionel MESSI`. The capitals are used only as a marker; stored text is title-cased:
  - `Lionel MESSI` → display `Lionel Messi`, given `Lionel`, family `Messi`
  - `Mohamed Ali BEN ROMDHANE` → display `Mohamed Ali Ben Romdhane`, given `Mohamed Ali`, family `Ben Romdhane`
  - fully capitalised (`MARQUINHOS`, `NUNO MENDES`) is a "known as" name → display `Marquinhos` / `Nuno Mendes`, given and family null
  - No particle rules (`de`, `van`, …) in v0.1.
- **Known gap:** the Club World Cup files strip accents (`Luis SUAREZ`, `JOAO MARIO`). v0.1 accepts this; accent-insensitive matching keeps scorer resolution working. Cross-team player linking (which could recover `Suárez` from Copa América squads) is deferred.

### Matches — key excludes kickoff

- Natural key: `(season_id, stage, home_team_id, away_team_id)`. Within a stage, a double round robin and the two legs of a knockout tie both swap home/away. `stage` is required because the same pairing can meet twice in one season in different stages: 11 cases in the in-scope data (e.g. Arsenal v PSG, UCL league phase and semi-final; Argentina v Canada, Copa América group and semi-final). With `stage` in the key there are zero collisions across all 13 source files (verified 2026-10-10). A postponement keeps its stage, so it still updates in place.
- `kickoff_utc` is an attribute, overwritten on each sync. The first time a sync observes a kickoff change, the previous value is copied to `original_kickoff_utc` (never overwritten afterwards).

### Goals — UUID kept, keyed by ordinal

- Goals keep a `uuid` PK (future features may reference a single goal) with a unique `(match_id, ordinal)`.
- Sync upserts goals by `(match_id, ordinal)` and deletes ordinals beyond the source's goal count for that match. Goals have no `external_ref` rows.

### Kickoff time zones

Source times are local wall-clock times without a zone. Resolution order per match line:

1. An explicit offset on the line (e.g. `Sat Jun 14 20:00 UTC-4` in `club-worldcup/more/2025_clubworldcup-full.txt`).
1. The zone configured for the source file in the sync config (e.g. `england/2024-25/1-premierleague.txt → Europe/London`).

Every source file MUST have a zone configured, verified by hand when the file is added. Sync fails if a match line has neither.

Source files, JSON mirrors and verified time zones live in `seeds/competitions.yaml`. Non-obvious ones: UEFA club competitions are written in CET/CEST (`Europe/Berlin`); Copa Libertadores in Brasília time (`America/Sao_Paulo`, checked against the 2025 final's published 18:00 BRT kickoff); WC 2022, Copa América 2024 and Club World Cup 2025 carry `UTC±N` on every line (`tz: inline`). The World Cup uses `worldcup/more/2022.txt` rather than `2022--qatar/cup.txt` because it has explicit offsets and the same capitalised-surname format as the Club World Cup.

A JSON mirror is used only when it is current: same match count as the text file, at least as many results, and no impossible values (a level shootout). As of 2026-10-10 that holds for the Premier League, Bundesliga and Ligue 1; La Liga and Serie A mirrors lack 10 results each, and the UCL mirror lacks the final and has garbled shootout scores.

Bracketed match tags are honoured: `[awarded]` keeps the awarded score as `COMPLETED`; `[postponed]` / `[cancelled]` set that status.

### Extra time and penalties

`home_score` / `away_score` are the score at the end of play (after extra time if played). `decided_by` records how the match ended; `home_pens` / `away_pens` hold the shootout score. The parser handles both observed notations: `3-3 a.e.t. (2-2, 2-0), 4-2 pen.` (worldcup) and `4-3 pen. (1-1, 1-0)` (copa-libertadores).

### Source coverage (verified 2026-10-10)

| Competition                           | Matches | Scorers | Squads | Source                                                          |
| ------------------------------------- | ------- | ------- | ------ | --------------------------------------------------------------- |
| 5 domestic leagues                    | ✅      | none    | none   | `england`, `espana`, `deutschland`, `italy`, `europe` (Ligue 1) |
| UCL / UEL / UECL 2024-25              | ✅      | none    | none   | `champions-league/2024-25/{cl,el,conf}.txt`                     |
| Copa Libertadores 2025                | ✅      | none    | none   | `south-america/copa-libertadores/2025_copal.txt`                |
| Club World Cup 2025                   | ✅      | ✅      | ✅     | `club-worldcup/more/2025_clubworldcup-{full,squads}.txt`        |
| World Cup 2022 · Euro 2024 · Copa Am. | ✅      | ✅      | ✅     | `worldcup/more/2022{,_squads}.txt`, `euro`, `copa-america`      |

## Ingestion architecture

```
   git clone openfootball/{england, ...}      SPARQL → wikidata.org
                  │                                  │
                  ▼                                  ▼
       ┌─────────────────────┐           ┌────────────────────┐
       │  openfootball       │           │  wikidata adapter  │
       │  text/JSON parser   │           │  (entity seed)     │
       └──────────┬──────────┘           └─────────┬──────────┘
                  │                                │
                  └──────────────┬─────────────────┘
                                 ▼
                       ┌───────────────────┐
                       │  Domain mapper    │
                       │  (canonical IDs,  │
                       │  reconciliation)  │
                       └─────────┬─────────┘
                                 ▼
                          ┌───────────────┐
                          │   Postgres    │
                          └───────────────┘
```

Sync is invoked manually via `just sync` (which delegates to `python -m football_api.sync`). It is **idempotent** end-to-end: each run reconciles source records against existing entities via `external_ref`, upserting as needed.

The Open Football **text DSL** parser handles the format used in the league repos. The JSON mirrors (where available and current) are preferred when present.

## API conventions

- URL prefix: `/v1`.
- All responses JSON. ISO 8601 timestamps in UTC, `Z` suffix.
- Pagination: `?limit=` (default 50, max 200) + `?cursor=` (opaque, base64-encoded).
- Nesting: `?expand=teams,scorers,venue` on resource endpoints.
- Filtering: explicit `*_id` query params per resource (`/v1/matches?season_id=…`).
- Every identifier is a UUID: path IDs (`/v1/teams/{id}`) and filters (`/v1/matches?competition_id=…&season_id=…&team_id=…`). A non-UUID value is a 422.
- Error envelope: `{ "error": { "code": "...", "message": "...", "details": {...} } }`.
- OpenAPI at `/openapi.json`; interactive docs at `/docs` (FastAPI built-in).

## Auth posture

In v0.1, the FastAPI application does **not** implement authentication or rate-limiting. The intended deployment topology assumes an API gateway in front that handles:

- API key validation
- Per-key rate limiting
- TLS termination
- Request logging for billing/analytics

**Local and compose deployments** bind to `127.0.0.1` only.

**Public deployments (decided 2026-10-10):** v0.1 may be exposed publicly with no authentication. That is acceptable because the API is read-only and serves public-domain (CC0) data: the risk is abuse, not disclosure. The reverse proxy in front of it acts as the minimal gateway: TLS, a per-client-IP rate limit and a cap on concurrent requests. API keys, per-key limits and request logging for billing still belong to the future gateway change. Deployment manifests are out of scope for this repository; it publishes multi-arch images and nothing more.

## Deployment

`docker-compose.yml` with two services:

- **api** — built from local `Dockerfile`, binds to `127.0.0.1:8000`.
- **postgres** — official `postgres:18.4` image, named volume for data.

`justfile` recipes: `up`, `down`, `logs`, `sync`, `psql`, `test`, `typecheck` — invoked as `just <recipe>`. Requires [`just`](https://github.com/casey/just) installed system-wide (`cargo install just`, `brew install just`, `apt install just`, etc.).

## Non-decisions / open

- **Real-time updates** — not in v0.1; manual sync only.
- **Versioning beyond /v1** — assume single version for now.
- **GraphQL** — explicitly deferred.
- **Observability** — stdout logging only; tracing/metrics later.

## Risks

| Risk                                                   | Mitigation                                                                             |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| Open Football text format edge cases break parser      | Pin to specific repo commits; vendor a snapshot when source breaks                     |
| Open Football data freshness lag                       | Documented as a known limitation; manual sync makes it explicit                        |
| Goal-scorer coverage uneven across competitions        | API contract marks scorer fields optional; document per-competition coverage           |
| Schema choices now constrain Phase 2 (lineups, events) | Keep schema additive; never store derived data that conflicts with future event tables |
| Accidental public exposure with no auth                | Bind to loopback only; document this in README under "Security posture"                |
