# Proposal

## Why

La Liga now has every season openfootball offers, each score checked against Wikipedia and refreshed on a schedule. The other four big domestic leagues still have only 2024-25 and nothing checking them. openfootball already has their earlier seasons, and English Wikipedia has a results grid for almost every one, so the La Liga approach carries over with no new reader or parser.

## What Changes

- **Full history for four leagues.** Each league lists every season openfootball has, including the one in progress:

  | League         | Seasons            | Count |
  | -------------- | ------------------ | ----- |
  | Premier League | 2000-01 to 2026-27 | 27    |
  | Bundesliga     | 2010-11 to 2026-27 | 17    |
  | Serie A        | 2013-14 to 2026-27 | 14    |
  | Ligue 1        | 2014-15 to 2026-27 | 13    |

  openfootball (CC0) stays the only data source.

- **Verification for every season with a usable grid.** Each season names its English Wikipedia article, and the existing verifier compares every score. That covers all 71 seasons. Serie A 2018-19's article had no links in its results table, so its teams couldn't be identified through Wikidata; the clubs have since been linked in the article (design D2).

- **Teams.** Every club that played these leagues in those seasons and isn't seeded yet is added to `seeds/teams.yaml` with its Wikidata QID. The rest of the roughly 150 missing openfootball spellings become aliases of clubs already seeded.

- **Cancelled fixtures.** Ligue 1 2019-20 was stopped after 279 matches. Its 101 unplayed fixtures are already stored as `CANCELLED`, and they get no verification status because neither source has a score for them.

- **Out of scope:** cups and tournaments (Champions League, Europa League, Conference League, Copa Libertadores, Club World Cup, World Cup, Euro, Copa América). Their Wikipedia articles have no single results grid, so they need a different reader. They're a follow-up change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `catalog`: Season catalog. The Premier League, Bundesliga, Serie A and Ligue 1 list every season their source provides, like La Liga.
- `match-verification`: the Wikipedia reference covers every configured domestic league season that names an article, not only La Liga.
- `ingestion`: Verification after sync. The example of a competition without a reference moves from the Premier League to a cup competition.

## Impact

- **Seeds:** `competitions.yaml` gains 67 seasons across the four leagues. `teams.yaml` gains the promoted and relegated clubs and their aliases.
- **Code:** no parser or verifier changes are expected. All 71 source files already parse to the expected match counts.
- **Data volume:** about 25,000 more matches.
- **Network:** a verified sync of all five leagues makes about two Wikipedia requests per season, about 170 in total, with the existing User-Agent, timeouts and retry rules.
- **Docs:** README coverage table and `openspec/config.yaml` scope context.
- **Out of scope:** which competitions the scheduled sync runs. Deployment configuration lives outside this repo.
