# Proposal

## Why

Spanish football is the first priority for more coverage, and openfootball/espana already ships the second tier for every season we load La Liga from, in the checkout sync clones today. Nothing loads it. It's CC0, verifiable against English Wikipedia like La Liga, and adds about 6,000 matches with no new source.

## What Changes

- **New competition: Segunda División** (Wikidata Q35615), `LEAGUE`, country `ES`, club teams, domestic.
- **13 seasons, 2012-13 to 2024-25,** from `espana/<label>/2-liga2.txt`, with the `football.json/<label>/es.2.json` mirror where it exists (2012-13 to 2020-21, 2024-25). Each has 22 clubs and 462 regular-season matches: 6,006 in all. The promotion play-offs aren't in the source.
- **Not included: 2025-26.** openfootball stopped updating it after round 12 (131 of 462 results), although the season ended in June 2026. It can be added when upstream catches up.
- **2024-25's last matchday:** 9 of its 11 matches have no score in either source file. They sync as scheduled and verification marks them `SOURCE_BEHIND`. Fix upstream in openfootball/espana, citing Wikipedia and the league's official results.
- **2018-19:** 21 matches are marked awarded in the source (CF Reus was expelled mid-season); the existing `awarded` flag covers them.
- **Ranking rules:** the RFEF rules La Liga uses (3/1/0; head-to-head points and goal difference, then goal difference and goals scored).
- **Verification:** each season names its English Wikipedia article (`2012–13 Segunda División` … `2024–25 Segunda División`). All 13 have a results grid the existing parser reads. In 2014-15 and 2015-16 the reader resolves 21 of the 22 clubs: English Wikipedia redirects UE Llagostera to its successor club, CF Badalona Futur, which Wikidata keeps as a separate item and which is already seeded (design D5).
- **Teams:** 56 of the 64 spellings already resolve to seeded clubs. 8 new clubs, identified through their English Wikipedia articles:

| openfootball spelling | Club                 | Wikidata |
| --------------------- | -------------------- | -------- |
| FC Barcelona B        | FC Barcelona Atlètic | Q10467   |
| CF Reus Deportiu      | CF Reus Deportiu     | Q1387573 |
| Real Madrid Castilla  | Real Madrid Castilla | Q12217   |
| Sevilla Atlético      | Sevilla Atlético     | Q950835  |
| Athletic Club B       | Athletic Bilbao B    | Q794970  |
| Lorca FC              | Lorca FC (2003)      | Q6463150 |
| Villarreal CF B       | Villarreal CF B      | Q1094113 |
| Real Sociedad B       | Real Sociedad B      | Q1067750 |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `catalog`: Competition and season catalog. Segunda División joins the domestic leagues, with seasons 2012-13 to 2024-25.

## Impact

- **Seeds:** `competitions.yaml` (1 competition, 13 seasons, ranking rules) and `teams.yaml` (8 clubs).
- **Code:** none expected. All 13 files parse to 462 matches with the existing parser; the 2025-26 file's `1. Round` labels also parse.
- **Docs:** README coverage table and the OpenSpec project context.
- **Upstream:** a PR to openfootball/espana for the 9 missing 2024-25 results.
