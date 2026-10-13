# Proposal

## Why

The five domestic leagues are complete and verified, but each country's other domestic competitions are missing: the traditional knockout cup open to the whole football pyramid, the league cup restricted to league clubs, and the super cup. openfootball (CC0) has the knockout cups and England's league cup for several recent seasons. Ingesting them gives every team its full domestic fixture list. Verifying them against Wikipedia needs a different reader, so that comes in a follow-up change.

## What Changes

- **Six domestic cups.** The seasons openfootball has, about 3,000 matches:

  | Cup             | Format       | Seasons                                         |
  | --------------- | ------------ | ----------------------------------------------- |
  | FA Cup          | knockout cup | 2018-19 to 2024-25 (7)                          |
  | EFL Cup         | league cup   | 2018-19 to 2024-25 (7)                          |
  | Copa del Rey    | knockout cup | 2020-21 to 2024-25 (5)                          |
  | DFB-Pokal       | knockout cup | 2018-19 to 2024-25 (7)                          |
  | Coppa Italia    | knockout cup | 2020-21 to 2024-25 (5)                          |
  | Coupe de France | knockout cup | 2024-25 (1, from round 7, as the source has it) |

- **Competition format.** Competitions get a `format` that tells these kinds apart, exposed in the API and filterable on `/v1/competitions`:

  - `LEAGUE`: round-robin.
  - `CUP`: knockout open to the national pyramid.
  - `LEAGUE_CUP`: knockout restricted to league clubs.
  - `SUPER_CUP`: champions' play-off, whose shape varies by country.
  - `TOURNAMENT`: a group or league phase followed by knockouts (the UEFA competitions, Copa Libertadores, Club World Cup, World Cup, Euro, Copa América).

  Every existing competition gets its format.

- **Knockout rounds.** Two new match stages:

  - `ROUND`: a numbered round before the named ones (the number goes in `matchday`).
  - `PRELIMINARY`: a preliminary round that is part of the competition proper, not qualifying.

  **BREAKING (API enum):** clients that switch over `stage` see two new values.

- **Repeated pairings.** A pairing can be played twice in one round with the same home team. In the 2023-24 FA Cup first round, Scarborough Athletic v Forest Green Rovers was drawn 1–1, and its replay was voided and replayed again at Scarborough. Matches get an `occurrence` number so both games are kept. Today the second one would overwrite the first.

- **Teams.** About 730 new openfootball spellings, mostly lower-division and amateur clubs, are added to `seeds/teams.yaml` with their Wikidata QIDs after review.

- **DFB-Pokal 2025-26 is left out.** openfootball's file stops after the second round: the round of 16 has no scores, and later rounds are `N.N.` placeholders. The `openliga/` conversions miss 10 to 20 matches per season. The season is added once the source completes it.

- **Not included:** super cups (Supercopa, Community Shield, DFL-Supercup, Supercoppa, Trophée des Champions). openfootball has none, and the same goes for other league cups such as the Coupe de la Ligue and the old Copa de la Liga. They are listed as deferred until a source exists.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `catalog`:
  - Competition catalog: the `format` field and its filter, and the six cups in scope.
  - Season catalog: the cups' seasons.
- `matches`: Match record. The `ROUND` and `PRELIMINARY` stages, and an `occurrence` number in the match identity.
- `ingestion`: Open Football text-format parser. It recognises the cups' round headers (`Round N`, `N. Round`, `Preliminary round`).

## Impact

- **Database:** one Alembic migration. It adds the `competition_format` enum and column (backfilled from the seeds on the next sync, with a default for existing rows), adds `ROUND` and `PRELIMINARY` to the `stage` enum, and adds `match.occurrence` (default 1) to the match unique key.
- **Code:** stage rules, the sync's match lookup, seeds schema, API schemas and `/v1/competitions` filter.
- **Seeds:** `competitions.yaml` (six cups, `format` on every entry) and `teams.yaml` (about 730 spellings).
- **API:** `format` on competitions, two new `stage` values and `occurrence` on matches. The changes are additive apart from the new enum values.
- **Out of scope:** Wikipedia verification of cups (follow-up change), and whether the scheduled sync includes cups (deployment configuration lives outside this repo).
