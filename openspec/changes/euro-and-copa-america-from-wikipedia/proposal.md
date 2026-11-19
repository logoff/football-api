# Proposal

## Why

The catalog is missing two Euros and 45 Copa Américas:

- **Euro 1984 and 1992:** openfootball lists their group matches without dates, so both editions are left out (the README names them as a gap).
- **Copa América:** openfootball/copa-america only has 2011, 2021 and 2024, out of 48 editions since 1916.

English Wikipedia has match boxes for all of them, and the model for reading pinned revisions already exists (`source-older-seasons-from-wikipedia`).

A spike on 2026-11-19 read every missing edition with the reader sync uses:

- **Read as they are:** 26 editions, including both Euros, with 15 matches each.
- **Fail on a heading:** the other 21.
  - `Results` or `Matches` holds a whole tournament played as one round robin (1916–1967).
  - `Finals` holds the two-legged finals of 1975 and 1979.
  - `Third-place match` names no stage (1987–2007).
- **Mislabelled:** `Final round` (1919–1963 round robins, and the four-team final group of 1989 and 1991) maps to `FINAL`, because the stage rules match the word "final". It reads without error but would be stored as a final.
- **Dates:** every box has one.
- **Teams:** only one isn't seeded, the CIS (Euro 1992, Q721418). There are no red links.
- **Size:** about 780 Copa América matches and 30 Euro matches.

## What Changes

- **UEFA European Championship 1984 and 1992**, from Wikipedia instead of openfootball, with dates. The Euro then has every edition from 1960 to 2024.
- **CONMEBOL Copa América, every edition openfootball lacks:** 45 editions from 1916 to 2019.
  - **Included:** the "extra" championships CONMEBOL counts (1935, 1941, 1945, 1946, 1956, and 1959 in Ecuador), and the Copa América Centenario (2016).
  - **Labels:** the two 1959 editions are labelled `1959 Argentina` and `1959 Ecuador`. Every other edition is labelled by its year.
  - **Left out:** 1967's qualifying round, as qualifying is for every other tournament.
  - **Not changed:** 2011, 2021 and 2024 stay on openfootball.
- **Round robins are group stages:** a tournament played as one round robin is stored as a single `GROUP` stage with no group name. A replayed pairing is then a play-off and stays out of the table, as for the 1954 and 1958 World Cups. 1989 and 1991 get a second group stage.
- **New optional season field `wikipedia_rounds`:** it renames a section heading to the round label it stands for, for example `Results: Group stage`. A listed heading the pages don't have fails the season, as `wikipedia_skip` does.
- **New optional season field `wikipedia_abandoned`:** a match abandoned and then replayed is stored `CANCELLED` without a score, so the replay is the result. Wikipedia gives the abandoned 1916 Argentina v Uruguay a 0–0 score and nothing marks it.
- **More stage variants:** `Finals` maps to `FINAL` and `Third-place match` to `THIRD_PLACE`.
- **Ranking rules for the Copa América before 2011:** two points for a win until 1993 and three from 1995. The tie-breakers of each era are checked once against Wikipedia's tables, as for the UEFA groups, without storing anything.
- **Not verified:** these seasons are sourced from Wikipedia, so Wikipedia can't also be their check.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `catalog`: the Euro lists every edition from 1960, and the Copa América every edition from 1916.
- `ingestion`: two more stage variants, a season field that renames headings to round labels, and one that marks abandoned matches that were replayed.

## Impact

- **Code:**
  - `wikipedia_season.py`: the `wikipedia_rounds` renames and the `wikipedia_abandoned` matches.
  - The stage rules in `text_parser.py`.
  - The seed model and the season fingerprint.
  - The pinning tool, which reads seeded seasons with the same options.
- **Seeds:**
  - 47 seasons with pins in `competitions.yaml`. The openfootball entries for Euro 1984 and 1992 aren't there to replace, since both were left out.
  - The Copa América's standings eras from 1916.
  - 1 team (CIS).
- **Database:** no schema change. About 810 more matches.
- **Docs:** the README coverage table, its notes on the Euro gap, and the `openspec/config.yaml` context.
- **Load on Wikipedia:** about 100 page revisions, fetched once and then cached.
