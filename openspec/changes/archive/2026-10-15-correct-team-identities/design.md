# Design

## Context

Teams have no key of our own. `find_team` resolves an entry through its spellings and QID, and refuses an entry that matches two teams. Matches are keyed by `(season, stage, home, away, occurrence)`. Their Open Football reference is `file#stage#home spelling#away spelling`, which is unique.

## Decisions

### D1. Release moved spellings before teams sync

For every entry with a QID, find its team. A spelling listed under another entry that still points at that team is deleted from `external_ref` before any entry is resolved. The entry it moved to then resolves through its own QID, or is created. The QID is the anchor because it identifies the club, while a spelling can be ambiguous.

### D2. A match follows its source listing

When neither the key nor the relabel fallback finds a match, the match its Open Football reference points at is reused if this sync hasn't seen it, and its teams are updated. Goals, verification and the UUID stay.

### D3. The seed's QID is the only one

Team sync deletes Wikidata references of the team other than the seeded QID, then ensures the seeded one.

### D4. Team seasons follow the source

After resolving a season's teams, `team_season` rows of that season for other teams are deleted.

## Risks / Trade-offs

- **[Risk] D1 deletes a reference that two entries list.** → `find_team` already refuses such seeds, and a spelling is listed once.
