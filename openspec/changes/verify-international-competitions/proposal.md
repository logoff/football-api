# Proposal

## Why

The eight international competitions (101 editions, about 6,500 matches) are ingested but not checked against anything, unlike the leagues and domestic cups. Their Wikipedia coverage is complete, but a season is spread over several articles: group-stage and knockout-phase articles for the UEFA competitions and the Copa Libertadores, and one article per group for the World Cup and the Euro.

## What Changes

- **Multi-article seasons.** For cups and tournaments, the reader also reads the sub-articles the season article links whose titles extend its own. It skips separate qualification tournaments, squads, other editions (women's, futsal) and non-match topics, and uses each match box once even if it appears in more than one article.
- **Seeds.** Each international edition names its season article, for example `2023–24 UEFA Champions League`, `2022 FIFA World Cup`, `1960 European Nations' Cup` or `UEFA Euro 2020` for the 2021 edition.
- **Verification** of the tournaments uses the existing box pairing (QIDs, then date) and statuses.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `match-verification`: "Reference results for domestic cups" becomes "Reference results for cups and tournaments", reading linked sub-articles and de-duplicating boxes.

## Impact

- **Code:** the Wikipedia client's box reading (sub-article discovery, exclusions, de-duplication) and the verifier's dispatch, where `TOURNAMENT` joins `CUP` and `LEAGUE_CUP`.
- **Seeds:** `wikipedia` titles for 101 editions.
- **Network:** about 2 to 12 article requests per season, roughly 600 for a full verified run of the tournaments.
- **Database and API:** no change.
