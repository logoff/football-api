# Init Football API v0.1

## Why

We're starting a SaaS that exposes a versatile, modern, easy-to-consume HTTP API for football (soccer) statistics. v0.1 is the smallest publishable surface that establishes the project's foundations — entities, schedules, and final results — sourced entirely from public-domain (CC0) data so we can ship without commercial licensing.

The intent is to validate the pipeline, the API ergonomics, and the self-hosting story end-to-end before investing in deeper data (lineups, cards, subs) or commercial data sources in later phases.

## What Changes

- Introduce an ingestion pipeline that loads data from the **openfootball/\*** GitHub repositories and seeds canonical entity identifiers via **Wikidata SPARQL**.
- Introduce a **REST API** (FastAPI + OpenAPI) exposing:
  - Catalog: competitions, seasons, teams, players, venues.
  - Matches: fixtures, results, and goal scorers (where the source provides them).
- Add a **manual sync command** (`just sync`) to refresh data on demand.
- Ship a **Docker Compose** deployment artifact (api + postgres), with locally built images.
- Establish project conventions: **uv** for package management, **pyright strict** for type checking.

## Scope

**In scope** — last completed edition of each competition. 13 competitions across four groupings:

Domestic club leagues (5):

- Premier League · La Liga · Bundesliga · Serie A · Ligue 1 (2024-25 season)

National-team tournaments (3):

- FIFA World Cup 2022 · UEFA Euro 2024 · Copa América 2024

Continental club tournaments (4):

- UEFA Champions League · UEFA Europa League · UEFA Conference League (2024-25 edition)
- Copa Libertadores (2025 edition — CONMEBOL calendar Feb–Nov)

Intercontinental club tournaments (1):

- FIFA Club World Cup 2025 (new 32-team format, USA, Jun–Jul 2025)

**Out of scope (deferred to later phases):**

- Africa Cup of Nations 2025 — no data in `openfootball/africa-cup` (repo holds only LICENSE + README).
- Copa Sudamericana 2025 — `openfootball/south-america` data is incomplete (group-stage results stop in April; knockout rounds are `N.N.` placeholders).
- FIFA Intercontinental Cup 2024 — not in openfootball (`internationals/more/intercontinental_cup/2024_…` is India's Hero Intercontinental Cup, a different tournament).
- Lineups, substitutions, cards, full event detail — follow-up change `add-match-events`, starting with Club World Cup 2025 (its `-full` file already carries lineups, subs, and cards).
- Live / in-play data.
- Player data beyond what Open Football provides (club squads remain partial).
- Logos, images, brand assets.
- Authentication and rate-limiting in the application layer (these will be terminated at an API gateway in a later change; the v0.1 app trusts its caller).
- Billing, multi-tenancy, public hosting.
- GraphQL surface.
- Automated ingestion scheduling.

## Impact

- **Specs (all new):** `catalog`, `matches`, `ingestion`.
- **Code:** green field — no prior implementation.
- **Operational:** introduces a Postgres dependency and a periodic manual data-sync chore.
- **Security posture:** no in-app auth in v0.1. Local and compose deployments bind to localhost only; public deployments are read-only, unauthenticated, and rate-limited at the reverse proxy (see design.md, "Auth posture"). API keys and per-key limits arrive with a later gateway change.
