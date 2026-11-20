# Design

## Context

- **How Wikipedia seasons are read:** from the match boxes of their pinned revisions, by `wikipedia_season.read_season` (`source-older-seasons-from-wikipedia`).
  - `round_label` drops the wrapper headings in `_NOT_A_STAGE`, then `normalize_stage` maps what's left to a stage.
  - Teams resolve by the QID of the article each box links. National team articles work the same way as club articles.
- **The gaps:**
  - The Euro's seed leaves out 1984 and 1992 because openfootball/euro lists their group matches without dates. Their semi-finals and final have dates.
  - openfootball/copa-america only has 2011, 2021 and 2024.
- **The spike, run on 2026-11-19 with that reader over all 47 missing editions:**
  - **Euro 1984 and 1992:** 15 boxes each, from the main article and its group, knockout and final sub-articles. Each has two groups of four, semi-finals and a final. Only one team isn't seeded: the CIS, Q721418.
  - **Copa América:** about 780 boxes, all with dates, every team already seeded.
    - **1916–1967, one round robin:** the whole tournament sits under one heading, `Final round` in 18 editions, `Results` in 10 and `Matches` in 1959 (Ecuador).
    - **Play-offs:** a tie on points for the title was settled by a play-off under `… / Play-off` (1919, 1922, 1937, 1949, 1953). `round_label` drops the `Play-off` heading, so the play-off lands in the same round as the rest.
    - **1975–1987, no host:** three groups played home and away (groups of three played once in 1987), then semi-finals. The finals of 1975 and 1979 sit under `Finals`: two legs and a play-off.
    - **1989 and 1991:** two groups of five, then a four-team final group under `Final round`.
    - **1993 onwards:** groups and knockouts. The third-place match is under `Third-place match` up to 2007, and `Third place play-off` from 2015.
    - **1967:** `Qualifying round / Results` holds four qualifying matches.
  - **What fails or is mislabelled:**
    - `Results` and `Matches` are wrapper headings or aren't stages, so 11 editions fail.
    - `Finals` and `Third-place match` don't match the stage rules, so 10 more editions fail.
    - `Final round` reads, but maps to `FINAL` because the rules match the word "final": 18 round robins and the 1989 and 1991 final groups would be stored as finals.
  - **1916:** Argentina v Uruguay on 16 July was abandoned at 0–0 after crowd trouble and replayed on 17 July. Wikipedia gives both boxes a 0–0 score and nothing marks the first one abandoned.

## Goals / Non-Goals

**Goals:**

- Every Euro and Copa América edition, with the same fields as the European Cup from Wikipedia: date, stage, teams, score, shootout and the awarded flag.
- Group tables for every edition, including the round robins, with ranking rules checked against Wikipedia's tables.

**Non-Goals:**

- **Qualifying.** As for every other tournament, only the final tournament is stored. That includes 1967's qualifying round.
- **Scorers, line-ups and venues from the boxes**, as in `source-older-seasons-from-wikipedia`.
- **Verifying these seasons.** Wikipedia is their source, so it can't also be their check.
- **The 1950 World Cup's final round.** openfootball labels it `Final Round`, so it is stored as `FINAL` too. Fixing it is a separate change to an openfootball season.

## Decisions

### D1. Editions and labels

- **Euro 1984 and 1992:** Wikipedia seasons in the existing competition, labelled `1984` and `1992`. Their openfootball files stay unused. The seed comment about left-out editions goes.
  - **Alternative: read openfootball and store the group matches without dates.** Rejected. Null kickoffs are for sources that never give dates, like La Liga's grids. Here Wikipedia gives every date, and a tournament with some dates and some missing can't answer `as_of`.
- **Copa América:** every edition Wikipedia's list counts, which is CONMEBOL's list. That includes the "extra" championships (1935, 1941, 1945, 1946, 1956, 1959 in Ecuador) and the Centenario.
  - **Labels:** the year, except the two 1959 editions, which are `1959 Argentina` and `1959 Ecuador`, both with `start_year` 1959. Labels must be unique within a competition, and naming both keeps neither one the "real" 1959.
  - **Articles:** `<year> South American Championship` up to 1967, `<year> Copa América` from 1975, and `Copa América Centenario`.
- **Pins:** one block per season from `just wikipedia-pins`, as for the European Cup.

### D2. More stage variants

`_STAGE_RULES` in `text_parser.py` gains two variants:

- **Third place:** `third[- ]place` instead of `third place`, so `Third-place match` maps to `THIRD_PLACE`.
- **Final:** `\bfinals?\b` instead of `\bfinal\b`, so `Finals` maps to `FINAL`. It stays after the semi-final and quarter-final rules, so `Semi-finals` is unaffected.

No stored openfootball label contains `Third-place` or a standalone `Finals`. The change is checked by syncing every openfootball season and comparing the stages before and after.

### D3. `wikipedia_rounds`

- **The field:** an optional season field, `wikipedia_rounds: {<heading>: <round label>}`, valid only with `wikipedia_source`.
  - `round_label` builds each box's label from its headings as it does now. Wherever a listed heading appears in the path, the given label replaces it, and the stage comes from that label.
  - Matching is case-insensitive and on the whole heading, as for `wikipedia_skip`.
  - A listed heading that none of the pinned pages has fails the season.
- **Where it's used:**
  - The round robins of 1916–1967: `Results`, `Matches` or `Final round` → `Group stage`. That's a `GROUP` stage with no group name, so `standings.py` builds one table from the teams that played each other.
  - 1989 and 1991: `Final round` → `Second group stage`, which `phase_of` already reads as phase 2.
- **Play-offs:** a play-off within a round robin repeats a pairing, so the existing group play-off rule leaves it out of the table, as for the 1954 and 1958 World Cups. 1922 and 1953 sit under `Results / Play-off`, which becomes `Group stage` with the rest.
- **Alternative: `LEAGUE` for the round robins.** Rejected. The `LEAGUE` table keeps every match, so the play-offs would count. And it's a tournament, not a league season.
- **Alternative: map `Final round` to `GROUP` in `normalize_stage`.** Rejected. "Final round" is also the name of knockout finals in other sources, and the stage rules can't tell them apart. The seed says it per season, where a reviewer can see it next to the article.

### D4. `wikipedia_abandoned`

- **The field:** an optional season field, `wikipedia_abandoned: [{date, home, away}]`, with home and away as QIDs.
  - The listed box is stored `CANCELLED` without a score. The replay is the result.
  - The table already leaves out `CANCELLED` matches, so the replay counts.
  - Sync numbers a pairing listed again after a listing without a score as the same game rescheduled. A `CANCELLED` listing now counts as a game of its own, so the abandoned match keeps its row (`occurrence` 1) next to the replay (2). No openfootball season lists a cancelled match and then the same pairing again in the same stage, so no stored match changes.
  - A listed match that no box holds fails the season.
- **Where it's used:** 1916 Argentina v Uruguay, 16 July. The pages are searched for "abandoned" while pinning, and any other case gets an entry too.
- **Alternative: drop the box.** Rejected. The match was kicked off and is part of the record; `CANCELLED` without a score says it didn't count.
- **Alternative: `awarded.yaml` with `played: PARTIAL`.** Rejected. Nothing was awarded: the match was replayed.

### D5. Fingerprint

`wikipedia_rounds` and `wikipedia_abandoned` are left out of the season dump while unset, as `wikipedia_skip` is. Adding them doesn't change any existing season's fingerprint.

### D6. Teams

The CIS (Q721418) is added as a national team. It stays separate from the Soviet Union and Russia, as Wikidata keeps them. The rest are already seeded from the World Cup.

### D7. Ranking rules

- **Copa América eras:** added from 1916, in front of the existing 2011 era.
  - **Points:** two for a win until 1993, three from 1995.
  - **Tie-breakers:** each era's are taken from the regulations as Wikipedia quotes them. In the round robins a tie for the title was played off, and the play-off is outside the table, so the tied teams come out `tied` unless goal average or difference split them.
- **Euro 1984 and 1992:** they use the existing 1960 era (two points, goal difference, goals scored).
- **Check:** every computed group table is compared once with Wikipedia's, without storing anything, as for the UEFA groups (172 of 172). The PR states the result and explains any difference.

### D8. Delivery

- **Two PRs:** the code (D2–D5, with tests), then the seasons, team, eras and docs (D1, D6, D7).

### D9. Awarded matches in boxes

- **Found while pinning:** the 1942 box for Argentina v Chile reads 0–0 with no mark. Chile left the pitch after 43 minutes and Argentina was given the win. The match was stored as a draw, and that table was the only one of 82 that differed from Wikipedia's.
- **The fix:** an `awarded.yaml` entry flags its match in every Wikipedia season, not just a grid season. A box that already says "awarded" is flagged either way. A stale entry fails the season, as for grids.
- **Alternative: store the draw and list it.** Rejected. The seed already exists for this, and a box is no better than a grid at saying a match was awarded.

## Risks / Trade-offs

- **Wikipedia errors become our data** → the same accepted risk as for the European Cup. The group-table comparison catches score errors in group matches. Knockout matches have no such check.
- **An abandoned match that isn't found** → it would be stored as a result, and its replay left out of the table as a play-off. Searching the pinned pages for "abandoned" while pinning, and the group-table comparison, should catch it.
- **Early championships' status** → some sources treat the extra editions as unofficial. CONMEBOL and Wikipedia count them, and each one is a season of its own, so a client can leave any of them out.
