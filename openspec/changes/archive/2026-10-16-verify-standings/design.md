# Design

## Context

Wikipedia renders standings with `Module:Sports table`: a `wikitable` whose header row has `Pos`, `Team`, `Pld`, `W`, `D`, `L`, `GF`, `GA`, `GD` and `Pts`, and whose team cell links the club or national team. League tables are in the season article. Group tables are in the season article or in the group sub-articles that match verification already follows.

## Decisions

### D1. One table builder

The API's table building moves into a shared async function, `season_tables(session, season, as_of)`. The endpoint and the verifier both use it, so they can never disagree about what our table is.

### D2. Reading Wikipedia's tables

- **Which tables:** any table whose header has `Team`, `Pld` (or `P`) and `Pts`. Older tables have no `Pos` column, and their row order is the position.
- **Columns** are mapped by header name, so column order and extra columns (`GD`, `Qualification`) don't matter.
- **Team:** the first non-flag link in the team cell, with notes (`(C)`, `(R)`) and footnotes ignored.
- **Pages:** the same as match verification: the season article plus its sub-articles (qualifying ones only when the season stores qualifying matches).
- **Duplicates:** tables with the same set of teams count once.

### D3. Pairing and comparing

- **Pairing:** an own final table pairs with the Wikipedia table holding exactly the same teams (by QID).
- **Comparing:** each row compares position, played, won, drawn, lost, goals for, goals against and points. Rows that results can't separate (`tied`) agree on any position within their tied block: references share such positions (World Cup 1950) or order them by lots. Reference rows with no games (withdrawn teams) are dropped before pairing.
- **Statuses:** a row agreeing on all of them is `VERIFIED`; any difference is `MISMATCH`, logged as `<season>: MISMATCH table <team>: stored <values>, wikipedia <values>`. Rows of an unpaired table are `UNCONFIRMED`.
- **In-progress tables** keep no status, and any earlier one is removed.

### D4. Storage

`standing_verification` holds (season, team, stage, phase, reference, status, checked_at), unique on the first five. A team is in exactly one table per stage and phase, so the row is identified without a group name, which unnamed groups don't have. Wikipedia's values are never stored.

### D5. What the first full run changed

Reviewing every mismatch of the first full run against official sources led to these changes:

- **Group play-offs leave the table.** The 1954 and 1958 World Cups list play-offs under the group's own label. In a group played once round, a pairing met again is a play-off.
- **Awarded winners** in `standings.yaml`, for an award that names a winner but keeps a level score (Bastia v Lyon 2016-17: the LFP gave Lyon the win and kept the 0-0).
- **Ranking rules:** no tie-breakers for the World Cup before 1962 (level teams shared a position or played off); goal average 1962–1966; goal difference only in 1970, then goals scored from 1974.
- **Curated decisions:**
  - Deductions: Almería 2014-15, Nice 2021-22, Montpellier 2023-24.
  - Orders: the five 1954/1958 play-offs, Ireland over the Netherlands by lots in 1990, and Nice over Reims in Ligue 1 2019-20 on head-to-head.

## Risks / Trade-offs

- **[Risk] A Wikipedia table is wrong** (it happens). → The mismatch is logged with both values and reviewed like a match mismatch: fix whichever source is wrong, upstream or on Wikipedia.
- **[Risk] Orders decided off the table** (play-offs, lots) appear as position mismatches if a curated order is missing. → That's the point: each one becomes a reviewed `standings.yaml` entry.
