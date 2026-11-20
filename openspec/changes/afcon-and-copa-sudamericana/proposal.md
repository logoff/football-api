# Proposal

## Why

Two competitions were deferred when the catalog was first scoped (`init-football-api-v0.1`):

- **Africa Cup of Nations:** `openfootball/africa-cup` holds no data.
- **Copa Sudamericana:** `openfootball/south-america`'s 2025 file was incomplete.

Looking again on 2026-11-20:

- **openfootball, Sudamericana 2012–2024:** a file per edition, all of them complete. Every match has a date, and every stage label maps. The only matches without a score are the 2016 final's two legs, marked `[cancelled]` (Chapecoense's air disaster). 2025 is still incomplete: 48 group matches without a score and no knockout rounds.
- **English Wikipedia, read with the existing match-box reader:**
  - **AFCON, every edition from 1957 to 2025 (35):** 851 boxes, all dated, and every team article with a QID. 30 African national teams aren't seeded.
  - **Sudamericana 2025:** 157 boxes, all with a score.
  - **Sudamericana 2002–2011:** the articles give boxes only for the finals and a few rounds, and use bracket tables for the rest. Not enough to read an edition.

## What Changes

- **New competition: CAF Africa Cup of Nations (Q83145),** `NATIONAL`, `CONTINENTAL`, `TOURNAMENT`. It gets the 35 editions from 1957 to 2025, from Wikipedia, unverified.
  - **Labels:** the edition's name, so `2021` for the edition played in January 2022, as CAF names it. `start_year` is the year of its first match.
  - **Round robins:** 1959's whole tournament and 1976's final round are group stages, through `rounds`.
  - **Not played:** 1957's Ethiopia v South Africa (South Africa disqualified) and Togo's three 2010 matches (withdrawn) are `CANCELLED` without a score.
- **New competition: CONMEBOL Copa Sudamericana (Q60585),** `CLUB`, `CONTINENTAL`, `TOURNAMENT`.
  - **2012–2024:** from openfootball, verified against Wikipedia like the Libertadores.
  - **2025:** from Wikipedia, unverified, since openfootball's file is incomplete. Its `First stage` is a preliminary round, through `rounds`.
  - **Left out:** 2002–2011, since Wikipedia has too few boxes, and 2026, which is in progress and has no openfootball file.
- **`Final stages` wraps rounds:** like `Final phase`, it names no stage, so the round under it decides. Today Sudamericana 2025's knockout play-offs read as finals.
- **Teams:** 30 national teams and the Sudamericana clubs that aren't seeded yet. These are 87 openfootball spellings and the 2025 Wikipedia QIDs, many of the same clubs.
- **Ranking rules:** standings eras for both competitions. They are taken from the regulations Wikipedia quotes and checked once against Wikipedia's group tables, as for the Copa América.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `catalog`: two more competitions and their seasons.
- `ingestion`: `Final stages` is a heading that wraps rounds.

## Impact

- **Code:** one entry in the wrapper headings of `wikipedia_season.py`.
- **Seeds:**
  - Two competitions in `competitions.yaml`, with their eras, 13 openfootball seasons and 36 pinned Wikipedia seasons.
  - The new teams in `teams.yaml`.
- **Docs:** README coverage, sources and the note on deferred competitions. The OpenSpec context.
- **Size:** about 850 AFCON matches and 1,700 Sudamericana matches.
