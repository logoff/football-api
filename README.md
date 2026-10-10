# Football API

HTTP API for football (soccer) statistics, built from public-domain [openfootball](https://github.com/openfootball) data (CC0) and Wikidata identifiers.

## Quickstart

```sh
just up && just sync
curl localhost:8000/v1/competitions
```

`just up` builds and starts the API and PostgreSQL. `just sync` clones the openfootball repositories into `.cache/sources`, applies migrations, and loads everything (about 20 seconds). Interactive docs: <http://localhost:8000/docs>.

## Requirements

- [`uv`](https://docs.astral.sh/uv/)
- [`just`](https://github.com/casey/just), installed system-wide (`cargo install just`, `brew install just`, `apt install just`, …). All project tasks are `just` recipes; run `just` to list them.
- Docker with Compose
- `git` (sync clones the source repositories)

## Security posture

**v0.1 has no authentication and no rate limiting.** Both are meant to live in an API gateway added in a later change. Until then:

- Every published port binds to `127.0.0.1` only (`docker-compose.yml`). Do not change this.
- Do not expose the API or PostgreSQL to any other network, and do not put it behind a public reverse proxy.
- The compose PostgreSQL password is a development default.

## Data coverage

13 competitions, last completed edition each:

| Competition                | Season  | Results | Goal scorers | Squads |
| -------------------------- | ------- | ------- | ------------ | ------ |
| Premier League             | 2024-25 | ✅      | none         | none   |
| La Liga                    | 2024-25 | ✅      | none         | none   |
| Bundesliga                 | 2024-25 | ✅      | none         | none   |
| Serie A                    | 2024-25 | ✅      | none         | none   |
| Ligue 1                    | 2024-25 | ✅      | none         | none   |
| UEFA Champions League      | 2024-25 | ✅      | none         | none   |
| UEFA Europa League         | 2024-25 | ✅      | none         | none   |
| UEFA Conference League     | 2024-25 | ✅      | none         | none   |
| CONMEBOL Copa Libertadores | 2025    | ✅      | none         | none   |
| FIFA Club World Cup        | 2025    | ✅      | ✅           | ✅     |
| FIFA World Cup             | 2022    | ✅      | ✅           | ✅     |
| UEFA European Championship | 2024    | ✅      | ✅           | ✅     |
| CONMEBOL Copa América      | 2024    | ✅      | ✅           | ✅     |

The API reports this in a `coverage` field on seasons, matches, and player listings, so "no scorers" is never mistaken for "no goals".

Known gaps:

- **Not included:** Africa Cup of Nations 2025 and FIFA Intercontinental Cup 2024 (no openfootball data), Copa Sudamericana 2025 (openfootball data is incomplete).
- **Unresolved scorers:** where a scorer's name matches no single squad member (e.g. two players called Rodríguez), the goal keeps the source name with no player link. About 1.6% of goals.
- **Accents:** World Cup and Club World Cup sources strip accents (`Angel Di Maria`).
- **Players are per team-season:** the same person at Euro 2024 and the Club World Cup is two player records for now.

## How it works

- `seeds/competitions.yaml`: the competitions, their source files, and each file's hand-verified time zone.
- `seeds/teams.yaml`: canonical teams, each with its Wikidata QID and every openfootball spelling. Sync fails on a team name not listed here. `tools/propose_teams.py` drafts entries for new sources; review them before committing.
- `just sync` is idempotent: running it again with unchanged sources leaves the database byte-for-byte identical, UUIDs included.
- Design and specs: `openspec/changes/init-football-api-v0.1/`.

## Development

```sh
just install     # uv sync
just up          # start postgres (+ api)
just test        # pytest; db tests create throwaway databases on that postgres
just typecheck   # pyright, strict
just psql        # database shell
```
