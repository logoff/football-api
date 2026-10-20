# Design

## Context

Team spellings map to teams through `external_ref(openfootball, spelling)`. Before this change a spelling meant one team for every season, and an alias moved to another team only through `release_moved_aliases`, which assumes the old team's own QID claims it.

## Decisions

### D1. Year-scoped spellings have their own key

`{name, from, until}` stores the reference `"<name> @<from>-<until>"` (`Yugoslavia @-1992`, `Yugoslavia @1993-`), so keys stay unique.

Resolution looks for a plain spelling first. Failing that, it takes the scoped key of that name whose years cover the season's start year. The common case keeps a single indexed lookup, and scoped names stay explicit in the seeds.

### D2. Seeds own every spelling

Team sync deletes a team's openfootball references that its entry no longer lists. Spellings come only from `teams.yaml`, so this can only remove what the seeds removed. Without it, the old plain `Yugoslavia` reference would keep resolving 1998 to the 1920–1992 team.

### D3. Squad players follow their listing

As matches already do, a squad player whose reference (`file#spelling#name`) exists while its (team, name) pair doesn't is reused. Its team-season moves to the new team. Without this the 1998 squad, synced since the squads change, would conflict.

### D4. Reference-only items translate, never identify

Verification maps each reference QID to the seeded team's own QID right after resolving Wikipedia titles. That covers results grids, match boxes and standings. Identity, sync and the API never see them.

**Alternative:** renaming the Dutch East Indies to Indonesia. Rejected: the side played under that name, and Indonesia may need its own entry later. The load check (D4's guard) would then flag the clash.

## Risks / Trade-offs

- **[Trade-off] The 1998 and 2000 sides show as "Serbia and Montenegro"**, a name adopted in 2003. → That's the team's current label in Wikidata; a season-scoped display name is a possible later refinement.
