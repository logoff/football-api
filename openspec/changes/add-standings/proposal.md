# Proposal

## Why

The API holds every result of 94 league seasons and 101 tournament editions, but not the tables those results produce: who leads, who went down, who finished top of a group. Standings are the most asked-for view of football data and the obvious next step now that the results are verified against Wikipedia.

Two things stop a table from being a plain sum of results:

- **Ranking rules differ by competition and era.** Two points for a win until the 1990s in tournaments, goal average in the 1960s, head-to-head first in La Liga, Serie A and UEFA groups but goal difference first in the Premier League and Bundesliga, and rules that change (Ligue 1 in 2025-26, the World Cup and Copa Libertadores in 2026).
- **Points are deducted off the pitch.** For example Everton (−8) and Nottingham Forest (−4) in the 2023-24 Premier League, or Juventus (−10) in the 2022-23 Serie A. openfootball records results, not sanctions.

## What Changes

- **New endpoint** `GET /v1/seasons/{id}/standings`: one table for a league season or a UEFA league phase, and one per group for tournament group stages (including the World Cup's second-round groups of 1974–1982). Optional `as_of` (a date) for the table on any day, and `expand=teams`.
- **Each row** has position, played, won, drawn, lost, goals for and against, goal difference, points, any point adjustments with their reason and source, and a `tied` flag when results alone can't separate teams (lots, fair play, a play-off).
- **Ranking rules in the seeds**: each competition names its points per result and its tie-breakers, by era (from a season label onward). A season can be ranked by points per game (Ligue 1 2019-20, stopped by COVID-19).
- **Curated adjustments** in a new seed `seeds/standings.yaml`: point deductions, and the final order of teams that results can't separate. Every entry carries its reason and an official source. Like `teams.yaml`, it's reviewed in pull requests.
- **Groups without a name in the source** (the 2023-24 Champions League and the 2023–2026 Copa Libertadores list group games by matchday) are found from who plays whom, and have no name.

Verifying final tables against Wikipedia's standings is a follow-up change (`verify-standings`). It will catch missing deductions and wrongly ordered rules.

## Capabilities

### New Capabilities

- `standings`: league and group tables computed from stored results, ranking rules, adjustments.

### Modified Capabilities

None. Match records and ingestion are unchanged.

## Impact

- **Code:** a standings module (grouping, ranking), the v1 router and schemas, seed loading for rules and adjustments.
- **Seeds:** a `standings` block per competition in `competitions.yaml`, and the new `seeds/standings.yaml`.
- **Database:** no change. Tables are computed on request from the stored matches; a season holds at most about 400 table matches.
- **API:** one new read-only endpoint.
