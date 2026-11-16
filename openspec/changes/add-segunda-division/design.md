# Design

## Context

openfootball/espana has a `2-liga2.txt` next to every `1-liga.txt` from 2012-13 on, and the football.json mirror has `es.2.json` for most of those seasons. The sync already clones both repositories. A check before writing this change found:

- **Parser:** every file from 2012-13 to 2024-25 parses to 462 matches with the current parser. 2018-19 has 21 matches marked awarded. 2024-25 has 453 scored matches. 2025-26 has 131.
- **Teams:** 65 spellings across the 14 files (including 2025-26), in the text files and the JSON mirror alike. 57 already resolve. The 8 that don't are new clubs, mostly reserve teams. The JSON mirror uses no spelling the text files don't.

## Goals / Non-Goals

**Goals:**

- Ingest and verify Segunda División's complete seasons with seed changes only.

**Non-Goals:**

- The promotion play-offs, which the source doesn't have.
- 2025-26, until openfootball completes it (D2).
- Line-ups and events: there's no `-full` file for the second tier.

## Decisions

### D1. Seeds in La Liga's shape

One competition, Wikidata Q35615, with the same `standings` rules as La Liga, since the RFEF's General Regulations govern both tiers. Each season sets `file: espana/<label>/2-liga2.txt`, `tz: Europe/Madrid`, `json` where `football.json/<label>/es.2.json` exists (not 2021-22 to 2023-24), and `wikipedia: "<YYYY–YY> Segunda División"`.

### D2. Only complete seasons

2025-26 stopped being updated after round 12, five months before the season ended. Listing it would serve 331 fixtures as scheduled for a season that's over, and verification would mark them all `SOURCE_BEHIND`. It's left out of the seed, with a comment, and goes back in once upstream catches up. 2024-25 is kept: 9 missing results out of 462 are a small, visible gap that verification already reports, and fixing them upstream is a small PR.

**Alternative considered:** listing 2025-26 like the in-progress seasons of the top leagues. Rejected: those are behind by days, not months.

### D3. Reserve teams are their own clubs

FC Barcelona B, Real Madrid Castilla, Sevilla Atlético, Athletic Club B, Villarreal CF B and Real Sociedad B each have their own Wikidata item and become their own team, never an alias of the first team. Lorca FC (Q6463150, founded 2003) is a different club from the seeded Lorca Deportiva CF. Names follow the seed's rule: the shortest of the Wikidata label and the source spellings, minus a trailing legal form (`Lorca FC` → `Lorca`).

### D4. Mismatch review

As for the other leagues: every `MISMATCH` from the integration run is reviewed and ends up as a parser bug (fixed, with a test), an openfootball error (reported upstream) or a Wikipedia error (recorded in the PR). Stored data is never patched by hand.

**Outcome:** the integration run synced 13 seasons of 462 matches and verified them with 26 Wikipedia requests in 1 min 52 s. 5,912 scores agree, 9 are `SOURCE_BEHIND` (2024-25), 1 is a `MISMATCH` and 84 can't be checked (D5).

- **Real Valladolid v Girona, 2014-15:** openfootball has 2–1, the Wikipedia grid 1–0. Wikipedia's own league table (Girona W24 D10 L8, 63–35) only adds up with 2–1. A Wikipedia grid error.
- **2013-14 table:** Wikipedia's table gives FC Barcelona B, Córdoba, Sabadell and Mirandés one goal more or less than its own grid, which agrees with openfootball on all 462 matches. A Wikipedia table error. Ponferradina and Girona also swap 15th and 16th. Four clubs finished on 51 points. In the mini-league between them, Ponferradina and Girona both have 9 points, and Ponferradina has the better goal difference (+2 to 0). That's our order, which follows the RFEF rule as written. Wikipedia puts Girona first on the result between the two. Left as reported.
- **2018-19 table, Reus:** LaLiga expelled Reus after the first half, and its 21 points were taken away. No official table turned up, but BDFutbol, both Wikipedias and the press agree, so `standings.yaml` has a −21 adjustment citing BDFutbol. The table then verifies 22 of 22.

### D5. UE Llagostera can't be verified

Wikidata has UE Llagostera (Q124751432, 1947–2022) and its successor CF Badalona Futur (Q2504228) as separate items. English Wikipedia has one article, under the successor's QID, and the 2014-15 and 2015-16 grids link to it. `reference_wikidata` can't map Q2504228 to Llagostera, because Badalona Futur is already seeded under that QID for the Copa del Rey. So Llagostera's 42 matches in each season stay unverified, and so do those two seasons' tables. The README names the gap.

**Alternative rejected:** choosing between two teams that share a reference QID by season (one ended in 2022, the other started then). It's a verifier change for 84 matches, and it can come later if another case turns up.
