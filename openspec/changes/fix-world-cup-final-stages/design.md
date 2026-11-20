# Design

## Context

- **How a stage is chosen:** `normalize_stage` tries its rules in order against a round label, and the first match wins. The final rule, `\bfinals?\b`, comes after the semi-final and quarter-final rules and before the group rule.
- **What it gets wrong:** two openfootball labels contain "final" without being finals.
  - **1950, `Final Round`:** six matches, a round robin of Uruguay, Brazil, Sweden and Spain.
  - **2026, `Bronze final`:** the third-place match.
- **What exists for Wikipedia:** `wikipedia_rounds` (`euro-and-copa-america-from-wikipedia` D3) reads a listed heading as another round label. It already turns the 1989 and 1991 Copa América final rounds into a second group stage.

## Goals / Non-Goals

**Goals:**

- Store the 1950 final round as a group, with a table checked against Wikipedia's.
- Store the 2026 Bronze final as `THIRD_PLACE`.

**Non-Goals:**

- **Changing what "Final round" means in the stage rules.** Some sources use it for knockout finals, so each season has to say what it means (`euro-and-copa-america-from-wikipedia` D3).
- **Deciding the 1950 title from the table.** Uruguay won on points. The table is computed by the existing 1950 rules, like any other.

## Decisions

### D1. `bronze` in the third-place rule

- The third-place rule runs before the final rule, so adding `bronze` to it is enough.
- No stored label contains `bronze` except the 2026 one. The full sync confirms that only that match changes stage.

### D2. One `rounds` field for every season

- **The field:** `wikipedia_rounds` is renamed `rounds`, valid for any season.
  - **Wikipedia season:** a listed heading is a section heading above a match box, as before.
  - **openfootball season:** it is a part of the round label. The parser joins the file's headings with `/` (`Group Matches / Group 1`), and each part that matches is replaced.
  - **Matching:** case-insensitive and on a whole heading, in both cases.
  - **A listed heading no match has:** fails the season.
- **Grid seasons reject it:** a league read from results grids has no headings, so `read_grid_season` fails on the field instead of ignoring it.
- **1950's label:** `Second group stage`. `phase_of` already reads it as phase 2, so the final round gets its own table, apart from the first-round groups. This is the label used for 1989 and 1991.
- **Alternative: a separate `openfootball_rounds`.** Rejected. It would be two fields for one idea, with the same rules.

### D3. Fingerprint

- `rounds` is left out of the season dump while it's unset, as the Wikipedia options are. Only seasons that set it see their fingerprint change: the 31 Copa América seasons, renamed, and 1950.
- The code change makes the next sync a full one anyway.

### D4. Identity

- Sync moves a match whose round changed to its new stage and keeps its id, as for a round renamed in the source (`test_relabelled_round_keeps_its_matches`). The full sync confirms it: all seven matches kept their ids.

## Risks / Trade-offs

- **openfootball renames its heading** → the 1950 season fails with an error naming the heading, rather than storing the round as a final again.
- **A client relying on seven `FINAL` matches** → the README says what changed. Every other final is unaffected.
