# Football API

HTTP API for football (soccer) statistics, built from public-domain [openfootball](https://github.com/openfootball) data (CC0) and Wikidata identifiers.

## Quickstart

```sh
just up && just sync
curl localhost:8000/v1/competitions
```

`just up` builds and starts the API and PostgreSQL. `just sync` clones the openfootball repositories into `.cache/sources`, applies migrations, and loads everything (about 20 seconds). Interactive docs: <http://localhost:8000/docs>.

## Container image

CI publishes the API image to GitHub Container Registry once type checks and tests pass:

| Trigger        | Tags                                     |
| -------------- | ---------------------------------------- |
| push to `main` | `main`, `sha-<commit>`                   |
| tag `v0.1.0`   | `0.1.0`, `0.1`, `latest`, `sha-<commit>` |

```sh
docker pull ghcr.io/logoff/football-api:latest
```

A version tag also creates a GitHub release whose notes list the image tags and the multi-arch digest.

By default the image runs migrations and then the API on port 8000. It needs `DATABASE_URL` (see the Security posture section before exposing it).

The same image can populate the database, e.g. from a scheduled job. Point `SOURCES_DIR` at a writable directory for the source checkouts:

```sh
docker run --rm -e DATABASE_URL=... -e SOURCES_DIR=/tmp/sources ghcr.io/logoff/football-api:latest \
  python -m football_api.sync --competition Q324867 --verify
```

The sync refuses to run until the API container has applied the migrations (exit code 3).

## Requirements

- [`uv`](https://docs.astral.sh/uv/)
- [`just`](https://github.com/casey/just), installed system-wide (`cargo install just`, `brew install just`, `apt install just`, …). All project tasks are `just` recipes; run `just` to list them.
- Docker with Compose
- `git` (sync clones the source repositories)

## Security posture

**v0.1 has no authentication.** The API is read-only and serves public-domain data, so the risk is abuse rather than disclosure.

- **Local and compose:** every published port binds to `127.0.0.1` only (`docker-compose.yml`). Keep it that way; the compose PostgreSQL password is a development default.
- **Public deployments:** put the API behind a reverse proxy that terminates TLS and enforces a per-client rate limit and a cap on concurrent requests. API keys and per-key limits are planned for a later gateway change.

## Data coverage

13 competitions. La Liga has every season openfootball publishes, up to the one in progress; the others have their last completed edition:

| Competition                | Seasons                 | Results | Goal scorers | Squads |
| -------------------------- | ----------------------- | ------- | ------------ | ------ |
| Premier League             | 2024-25                 | ✅      | none         | none   |
| La Liga                    | 2012-13 to 2026-27 (15) | ✅      | none         | none   |
| Bundesliga                 | 2024-25                 | ✅      | none         | none   |
| Serie A                    | 2024-25                 | ✅      | none         | none   |
| Ligue 1                    | 2024-25                 | ✅      | none         | none   |
| UEFA Champions League      | 2024-25                 | ✅      | none         | none   |
| UEFA Europa League         | 2024-25                 | ✅      | none         | none   |
| UEFA Conference League     | 2024-25                 | ✅      | none         | none   |
| CONMEBOL Copa Libertadores | 2025                    | ✅      | none         | none   |
| FIFA Club World Cup        | 2025                    | ✅      | ✅           | ✅     |
| FIFA World Cup             | 2022                    | ✅      | ✅           | ✅     |
| UEFA European Championship | 2024                    | ✅      | ✅           | ✅     |
| CONMEBOL Copa América      | 2024                    | ✅      | ✅           | ✅     |

The API reports this in a `coverage` field on seasons, matches, and player listings, so "no scorers" is never mistaken for "no goals".

### Verification

openfootball is the only data source. La Liga scores are additionally checked against the results grid of the English Wikipedia season article, so a wrong score in either source shows up instead of passing silently. Wikipedia is read only to compare: none of its values are stored or served.

Each La Liga match gets a `verification` object in the API (`null` elsewhere), and `/v1/matches?verification=MISMATCH` lists the disagreements:

| Status          | Meaning                                                   |
| --------------- | --------------------------------------------------------- |
| `VERIFIED`      | both sources have the same score                          |
| `MISMATCH`      | the scores differ; the stored score is kept as it is      |
| `UNCONFIRMED`   | openfootball has a result that Wikipedia doesn't have yet |
| `SOURCE_BEHIND` | Wikipedia has a result that openfootball doesn't have yet |

Statuses are recomputed on every `--verify` run, and each disagreement is logged with both scores.

Known gaps:

- **Not included:** Africa Cup of Nations 2025 and FIFA Intercontinental Cup 2024 (no openfootball data), Copa Sudamericana 2025 (openfootball data is incomplete).
- **Unresolved scorers:** where a scorer's name matches no single squad member (e.g. two players called Rodríguez), the goal keeps the source name with no player link. About 1.6% of goals.
- **Accents:** World Cup and Club World Cup sources strip accents (`Angel Di Maria`).
- **Players are per team-season:** the same person at Euro 2024 and the Club World Cup is two player records for now.

## How it works

- `seeds/competitions.yaml`: the competitions, their source files, and each file's hand-verified time zone.
- `seeds/teams.yaml`: canonical teams, each with its Wikidata QID and every openfootball spelling. A season whose file uses a team name not listed here fails to sync. `tools/propose_teams.py` drafts entries for new sources; review them before committing.
- `just sync` is idempotent: running it again with unchanged sources leaves the database byte-for-byte identical, UUIDs included.
- Design and specs: `openspec/changes/init-football-api-v0.1/`.

### Sync command

`just sync` runs `python -m football_api.sync` over every competition. It can also be scoped and run unattended, e.g. from a scheduler:

```sh
python -m football_api.sync --competition Q324867 --verify   # La Liga only, then verify it
just sync-competition Q324867 --verify                       # the same, after local migrations
```

- `--competition QID`: only this competition (its Wikidata QID, as in `seeds/competitions.yaml`). Repeatable. Default: all of them.
- `--verify`: after syncing, check the scores of every season that names a reference (see [Verification](#verification)).
- `--no-refresh`: use the existing source checkouts without fetching.

Each season is synced in its own transaction, so a broken file costs only that season, and the log has one line per season. The sync never runs migrations: the API container applies them on start.

| Exit code | Meaning                                                                     |
| --------- | --------------------------------------------------------------------------- |
| 0         | every requested season synced; verification findings never fail a run       |
| 1         | a season, or the seed step, failed (the other seasons are still committed)  |
| 2         | usage error, e.g. an unknown QID; nothing was written                       |
| 3         | the database schema isn't at the code's migration head; nothing was written |
| 4         | another sync is running against the same database; nothing was written      |

## Development

```sh
just install     # uv sync
just up          # start postgres (+ api)
just test        # pytest; db tests create throwaway databases on that postgres
just typecheck   # pyright, strict
just psql        # database shell
```

## License

The code is released under the [MIT License](LICENSE). The data it serves comes from [openfootball](https://github.com/openfootball) and [Wikidata](https://www.wikidata.org/), both CC0 (public domain).
