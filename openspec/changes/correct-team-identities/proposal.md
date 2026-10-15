# Proposal

## Why

Checking the international competitions against Wikipedia exposed teams with the wrong identity in `seeds/teams.yaml`:

- **Spellings under the wrong club.** Five spellings of South American and Mexican clubs were listed under a different club with a similar name:

  - `América (MEX)` under América Futebol Clube (Brazil).
  - `Barcelona (ECU)` under FC Barcelona.
  - `Everton (CHI)` under Everton.
  - `Liverpool (URU)` and `Liverpool FC (URU)` under Liverpool of England.
  - `Universidad Católica (CHI)` under Universidad Católica del Ecuador.

  Their matches were stored against that other club.

- **Wrong Wikidata items.** Four clubs pointed at a different Wikidata item than their Wikipedia article: Juan Aurich, Deportivo Lara, SC Dnipro-1 and Breiðablik.

Correcting the seeds alone isn't enough. The moved spelling still resolves to the old team, so the entry it moved to would take over that team's row. A corrected QID would sit next to the wrong one, and the old club would stay in the seasons it never played.

## What Changes

- **Seeds:** the five spellings move to their own clubs. Three new entries: Club América, Everton de Viña del Mar and Liverpool F.C. (Montevideo). The other two move to the existing entries for Barcelona SC and Club Deportivo Universidad Católica. The four Wikidata items are corrected.
- **Sync:**
  - A spelling still pointing at a team another entry claims by QID is released before teams sync.
  - A match whose source listing now resolves to other teams follows it, keeping its UUID.
  - A corrected QID replaces the old one.
  - Teams no longer in a season's source leave that season.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ingestion`: Idempotency. Teams' references follow seed corrections, and a match follows its source listing.

## Impact

- **Code:** `sync.py` (team sync, match lookup, team-season cleanup).
- **Data:** `seeds/teams.yaml`. Production data is corrected by the next full sync, with no migration. Match UUIDs are kept.
