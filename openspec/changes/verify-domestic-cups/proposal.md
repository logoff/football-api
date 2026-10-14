# Proposal

## Why

The six domestic cups (FA Cup, EFL Cup, Copa del Rey, DFB-Pokal, Coppa Italia, Coupe de France: 32 seasons, about 3,200 matches) are ingested but not checked against anything, unlike the leagues. Cup articles have no results grid, but English Wikipedia lists every cup match in a match box. A survey of all 32 season articles found that two templates, "Football box collapsible" and "Football box", cover every match openfootball has, give or take a voided or walkover tie it leaves out.

## What Changes

- **A cup reader** for those two templates in each season article. For every box it reads the date, both clubs (by their linked article, hence their Wikidata QID), and the result: full-time score including extra time, plus the shootout score when there is one. Boxes without a result (`w/o`, `Walkover`, `Void`, `Bye`, `v`) give no reference score. Aggregate scores in two-legged ties are ignored, because each leg is compared on its own.
- **Verification of cup seasons**, with the same statuses, report and guarantees as the leagues:
  - **Pairing:** a stored match is paired with the box of the same home and away clubs, and, when that pairing occurs more than once in the season, of the same date.
  - **Shootouts:** when both sources have a shootout score, it must match too.
- **Seeds:** each of the 32 cup seasons names its article (`YYYY–YY FA Cup`, …).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `match-verification`:
  - New requirement "Reference results for domestic cups".
  - Verification status per match also compares shootout scores when both sources have one.

## Impact

- **Code:** a match-box reader next to the grid reader. `verify_seasons` picks the reader by competition format (`LEAGUE` → grid, `CUP`/`LEAGUE_CUP` → match boxes). Pairing by QIDs and date.
- **Seeds:** `wikipedia` titles on the cup seasons.
- **Network:** about two requests per cup season, so about 64 for a verified cup run.
- **Database and API:** no change. Statuses use the existing table and field.
- **Out of scope:** the UEFA and FIFA tournaments, which use the same templates and are a follow-up once cups work. Also whether the scheduled run includes cups.
