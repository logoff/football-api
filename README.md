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

19 competitions. The five domestic leagues have every season openfootball publishes, up to the one in progress, each checked against Wikipedia (see [Verification](#verification)). The domestic cups have every complete season openfootball publishes, also checked against Wikipedia. The others have their last completed edition. Each competition has a `format`: `LEAGUE`, `CUP` (knockout open to the national pyramid), `LEAGUE_CUP` (knockout for league clubs only), `SUPER_CUP` or `TOURNAMENT` (a group or league phase, then knockouts).

| Competition                | Format     | Seasons                 | Results | Verified | Goal scorers | Squads |
| -------------------------- | ---------- | ----------------------- | ------- | -------- | ------------ | ------ |
| Premier League             | LEAGUE     | 1992-93 to 2026-27 (35) | ✅      | ✅       | none         | none   |
| La Liga                    | LEAGUE     | 2012-13 to 2026-27 (15) | ✅      | ✅       | none         | none   |
| Bundesliga                 | LEAGUE     | 2010-11 to 2026-27 (17) | ✅      | ✅       | none         | none   |
| Serie A                    | LEAGUE     | 2013-14 to 2026-27 (14) | ✅      | ✅       | none         | none   |
| Ligue 1                    | LEAGUE     | 2014-15 to 2026-27 (13) | ✅      | ✅       | none         | none   |
| FA Cup                     | CUP        | 2018-19 to 2024-25 (7)  | ✅      | ✅       | none         | none   |
| EFL Cup                    | LEAGUE_CUP | 2018-19 to 2024-25 (7)  | ✅      | ✅       | none         | none   |
| Copa del Rey               | CUP        | 2020-21 to 2024-25 (5)  | ✅      | ✅       | none         | none   |
| DFB-Pokal                  | CUP        | 2018-19 to 2024-25 (7)  | ✅      | ✅       | none         | none   |
| Coppa Italia               | CUP        | 2020-21 to 2024-25 (5)  | ✅      | ✅       | none         | none   |
| Coupe de France            | CUP        | 2024-25                 | ✅      | ✅       | none         | none   |
| UEFA Champions League      | TOURNAMENT | 2024-25                 | ✅      | none     | none         | none   |
| UEFA Europa League         | TOURNAMENT | 2024-25                 | ✅      | none     | none         | none   |
| UEFA Conference League     | TOURNAMENT | 2024-25                 | ✅      | none     | none         | none   |
| CONMEBOL Copa Libertadores | TOURNAMENT | 2025                    | ✅      | none     | none         | none   |
| FIFA Club World Cup        | TOURNAMENT | 2025                    | ✅      | none     | ✅           | ✅     |
| FIFA World Cup             | TOURNAMENT | 2022                    | ✅      | none     | ✅           | ✅     |
| UEFA European Championship | TOURNAMENT | 2024                    | ✅      | none     | ✅           | ✅     |
| CONMEBOL Copa América      | TOURNAMENT | 2024                    | ✅      | none     | ✅           | ✅     |

Cups start where the source does: the FA Cup at Round 1 (the first round proper), the Coupe de France at round 7. Numbered cup rounds have stage `ROUND` with the round's number in `matchday`, and a preliminary round that is part of the competition proper has stage `PRELIMINARY`; clients that switch over `stage` should expect both. A pairing played again with the same home team in the same round (FA Cup 2023-24: Scarborough Athletic v Forest Green Rovers, drawn and then replayed at Scarborough after a voided replay) is two matches with `occurrence` 1 and 2.

The Premier League's 1992-93 to 1997-98 and 1999-00 seasons have dates but no kickoff times in the source; their `kickoff_utc` is midnight UTC on the match date.

Ligue 1 2019-20 was stopped after 279 matches; its 101 unplayed fixtures are listed as `CANCELLED`.

Matches decided off the pitch (a forfeit or a disciplinary decision) have `awarded: true` and keep the score the source records. That's usually the awarded score (Union Berlin v Bochum 2024-25, `0-2`), but for SC Bastia v Olympique Lyonnais 2016-17 it's the 0–0 at abandonment: the LFP credited Lyon with the win and no goals.

The API reports this in a `coverage` field on seasons, matches, and player listings, so "no scorers" is never mistaken for "no goals".

### Verification

openfootball is the only data source. Domestic league scores are additionally checked against the results grid of the English Wikipedia season article, and domestic cup scores (including penalty shootouts) against the article's match boxes, so a wrong score in either source shows up instead of passing silently. Wikipedia is read only to compare: none of its values are stored or served.

Each verified match gets a `verification` object in the API (`null` elsewhere), and `/v1/matches?verification=MISMATCH` lists the disagreements:

| Status          | Meaning                                                   |
| --------------- | --------------------------------------------------------- |
| `VERIFIED`      | both sources have the same score                          |
| `MISMATCH`      | the scores differ; the stored score is kept as it is      |
| `UNCONFIRMED`   | openfootball has a result that Wikipedia doesn't have yet |
| `SOURCE_BEHIND` | Wikipedia has a result that openfootball doesn't have yet |

Statuses are recomputed on every `--verify` run, and each disagreement is logged with both scores. An awarded match recorded with a level score isn't compared, since the source names no winner.

Known gaps:

- **Not included:** Africa Cup of Nations 2025 and FIFA Intercontinental Cup 2024 (no openfootball data), Copa Sudamericana 2025 (openfootball data is incomplete).
- **Super cups and other league cups:** openfootball has no super cups (Supercopa, Community Shield, DFL-Supercup, Supercoppa, Trophée des Champions) and no league cup besides the EFL Cup.
- **DFB-Pokal 2025-26:** openfootball's file stops after round 2, so the season isn't included yet.
- **EFL Cup 2020-21:** Leyton Orient v Tottenham Hotspur (called off and awarded to Tottenham) has no result in the source, so the season shows as in progress.
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
