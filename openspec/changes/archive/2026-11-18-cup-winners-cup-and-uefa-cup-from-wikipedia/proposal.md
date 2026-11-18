# Proposal

## Why

The UEFA Europa League only goes back to 2020-21, openfootball's first season, and the Cup Winners' Cup isn't in the catalog at all. English Wikipedia has match boxes for both, the same way it has them for the European Cup, which is already read from pinned revisions (`source-older-seasons-from-wikipedia`).

A spike on 2026-11-18 read every season of both competitions with the reader sync uses:

- Cup Winners' Cup, 1960-61 to 1998-99: 39 seasons, 2,296 boxes.
- UEFA Cup, 1971-72 to 2008-09, and Europa League, 2009-10 to 2019-20: 49 seasons, 8,054 boxes. 1996-97 still has to be added.

Every box has a date. Only two things stop the sync: one club article that doesn't exist (a red link), and section wrappers that map to the wrong stage.

## What Changes

- **UEFA Cup Winners' Cup, 1960-61 to 1998-99**, as a new competition: `CLUB`, `CONTINENTAL`, `TOURNAMENT`, Wikidata Q40241. It was a knockout every season, like the European Cup before 1991-92, which is also `TOURNAMENT`.
- **UEFA Cup, 1971-72 to 2008-09, and Europa League, 2009-10 to 2019-20**, join the existing Europa League competition, since Wikidata has one item (Q18760) for both, as it does for the European Cup and the Champions League.
- **Same scope as the Champions League:**
  - Up to 1993-94 every round is included, preliminary and qualifying ones too, since all of them were the competition proper.
  - From 1994-95 the qualifying and preliminary rounds are left out. That matches the Champions League from 1994-95 and openfootball's Europa League from 2020-21, which starts at the group stage.
  - The Inter-Cities Fairs Cup (1955-71) isn't a UEFA competition and stays out.
- **Section wrappers:** `Final phase`, `Tournament phase` and `Qualifying phase` hold rounds without being one. They name no stage, as `Knockout phase` already doesn't. Until now, `Final phase / Third round` mapped to `FINAL`.
- **Two new optional season fields for Wikipedia seasons:**
  - `wikipedia_skip`: sections whose boxes aren't read, which is how the qualifying rounds from 1994-95 are left out.
  - `wikipedia_qids`: QIDs for club names a box links to an article that doesn't exist. In 1996-97, `Khazri Buzovna` (Q2338519) is a red link.
- **Data:**
  - About 357 clubs are added to `seeds/teams.yaml` with their QIDs.
  - Walkovers are stored `CANCELLED`, as for the Champions League. The spike found 6 in the UEFA Cup.
  - The awarded boxes get `seeds/awarded.yaml` entries: Hajduk Split v Marseille 1987-88, Fiorentina v Grasshopper 1998-99, Celta v Red Star 2000-01 and Rapid București v Paris Saint-Germain 2001-02.
- **Group-stage ranking rules:** the UEFA Cup groups of five played once (2004-05 to 2008-09), and the Europa League groups from 2009-10 to 2019-20. They're checked once against Wikipedia's tables, without storing anything.
- **Not verified:** as for the Champions League, these seasons are sourced from Wikipedia, so Wikipedia can't also be their check.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `catalog`: the Cup Winners' Cup joins the in-scope competitions. The Europa League's seasons go back to 1971-72.
- `ingestion`: section wrappers name no stage, and two new optional season fields are added: sections that aren't read, and QIDs for unlinked clubs.

## Impact

- **Code:**
  - `wikipedia_season.py`: the wrapper headings, skipped sections, and QID overrides before the title → QID lookup.
  - The seed model and the season fingerprint.
  - The pinning tool, which reads seeded seasons with the same options.
- **Seeds:**
  - 1 competition and 88 seasons with pins in `competitions.yaml`.
  - About 357 teams.
  - The Europa League's standings eras from 2004.
  - About 4 awarded entries.
- **Database:** no schema change. Roughly 9,900 more matches, about 13% more.
- **Docs:** the README coverage rows and the `openspec/config.yaml` context.
- **Load on Wikipedia:** about 160 page revisions, fetched once and then cached.
