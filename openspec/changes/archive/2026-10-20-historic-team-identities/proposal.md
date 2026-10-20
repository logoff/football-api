# Proposal

## Why

The last unverified international rows come from two historic sides whose identity differs between openfootball, Wikidata and Wikipedia:

- **FR Yugoslavia.** It played the 1998 World Cup and Euro 2000 as "Yugoslavia", and openfootball names it so. Those matches therefore sit with the 1920–1992 Yugoslavia (Q188363). Wikidata and Wikipedia treat that side as Serbia and Montenegro (Q1131732, 1992–2006, called FR Yugoslavia until 2003), which we already seed for 2006.
- **Dutch East Indies.** The 1938 World Cup side is seeded with its own item (Q2535606). Wikipedia links it as Indonesia (Q657451), which FIFA credits with the appearance.

## What Changes

- **Year-scoped spellings:** a `teams.yaml` spelling can apply only from or until a season's start year.
  - `Yugoslavia` names the 1920–1992 team until 1992, and Serbia and Montenegro from 1993.
  - The 1998 and 2000 matches and squad players move to Serbia and Montenegro, keeping their UUIDs.
- **Removed spellings are dropped:** a spelling removed from an entry no longer names its team. That's needed so the old plain `Yugoslavia` reference stops winning.
- **Reference-only items:** `reference_wikidata` lists the Wikidata items verification references use for a team. The Dutch East Indies stays as it played, and verification accepts Indonesia's item as the same side.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ingestion`: year-scoped team spellings; matches and squad players follow their listing to a new team.
- `match-verification`: reference-only Wikidata items.

## Impact

- **Code:** seed models and checks, team resolution (season year), squad sync, verification's QID mapping.
- **Seeds:** `teams.yaml` (Yugoslavia, Serbia and Montenegro, Dutch East Indies).
- **Data:** 8 matches and 2 squads move team. No migration.
