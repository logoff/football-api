# Proposal

## Why

The Premier League starts at 2000-01 in our data, but openfootball also has its first eight seasons, 1992-93 to 1999-00, in `england/archive/1990s/`. The extension in `extend-and-verify-top-leagues` looked only at the per-season folders, so it missed them. English Wikipedia has a results grid for each of those seasons, so they can be verified the same way.

## What Changes

- **Eight more Premier League seasons:** 1992-93 to 1999-00, from `england/archive/1990s/<label>/1-premierleague.txt`. The first three have 22 clubs and 462 matches each, the rest 20 clubs and 380 matches. That's 3,286 matches, all played, and it brings the Premier League to 35 seasons, from its first.
- **Verification:** each season names its English Wikipedia article (`1992–93 FA Premier League` … `1999–2000 FA Premier League`). The existing verifier compares every score.
- **Teams:** 21 new openfootball spellings of clubs already seeded (for example `Sheffield Wed`, `Newcastle Utd`), and one new club: Wimbledon F.C. (Q19482). It's the club that played in the Premier League until 2000 and later became MK Dons, which Wikidata keeps as a separate item, and it's distinct from AFC Wimbledon.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `catalog`: Season catalog. The Premier League lists every season from 1992-93.

## Impact

- **Seeds:** `competitions.yaml` (8 seasons) and `teams.yaml` (21 aliases and 1 club).
- **Code:** none. All eight files already parse to the expected match counts, and kickoffs without a time are handled by the existing date-only rule.
- **Docs:** README coverage and the OpenSpec scope context.
- **Workflow:** this change and `add-domestic-cups` both modify the Season catalog requirement. This delta carries the cups text too, so `add-domestic-cups` must be archived first.
