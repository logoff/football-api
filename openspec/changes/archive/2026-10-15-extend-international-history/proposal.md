# Proposal

## Why

The domestic leagues and cups have their full openfootball history, but the eight international competitions still have one edition each. openfootball goes much further back:

- the World Cup to 1930 and the Euro to 1960,
- the Champions League to 2011-12 and the Copa Libertadores to 2012,
- the Club World Cup to 2000.

That's about 7,000 matches of history the API doesn't serve. This change ingests it. Verification against Wikipedia, which needs several articles per season for these competitions, is a follow-up change.

## What Changes

- **Full history, including editions in progress:**

  | Competition                | Editions           |
  | -------------------------- | ------------------ |
  | UEFA Champions League      | 2011-12 to 2025-26 |
  | UEFA Europa League         | 2020-21 to 2024-25 |
  | UEFA Conference League     | 2021-22 to 2024-25 |
  | CONMEBOL Copa Libertadores | 2012 to 2026       |
  | FIFA Club World Cup        | 2000 to 2025       |
  | FIFA World Cup             | 1930 to 2026       |
  | UEFA European Championship | 1960 to 2024       |
  | CONMEBOL Copa América      | 2011, 2021, 2024   |

  An edition whose source gives no date for some of its matches is left out and listed as a known gap (Euro 1992 is one).

- **Parser.** The older tournament files use layouts the parser doesn't read yet:

  - dates without a weekday (`June 14`, `Jun 14`), alone or at the start of a match line, with an optional time and venue;
  - German group headers (`Gruppe G`, `Gruppe 1`);
  - ordinal rounds (`1st Round`, `First round`);
  - fifth-place matches.

- **New stage `FIFTH_PLACE`** for the Club World Cup's placement match. **BREAKING (API enum):** clients that switch over `stage` see a new value.

- **Teams.** About 500 new openfootball spellings (European and South American clubs, and historic national teams such as West Germany, the Soviet Union, Yugoslavia and Czechoslovakia), each with its own Wikidata QID after review.

- **Squads** stay as they are: only the editions that already have them.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `catalog`: Season catalog. The international competitions list their full history.
- `matches`: Match record. Adds the `FIFTH_PLACE` stage.
- `ingestion`: Open Football text-format parser. Covers the older layouts and headers.

## Impact

- **Database:** one Alembic migration adds `FIFTH_PLACE` to the `stage` enum.
- **Code:** the text parser (date forms, line-prefixed dates, stage rules).
- **Seeds:** `competitions.yaml` (about 100 seasons) and `teams.yaml` (about 500 spellings).
- **Data:** about 7,000 matches. The nightly league run is unaffected. Keeping Champions League 2025-26 and Libertadores 2026 current needs the scheduled run to include them, which is decided outside this repo.
