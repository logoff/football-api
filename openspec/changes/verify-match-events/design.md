# Design

## Context

Stored events (change `add-match-events`) cover every World Cup and Club World Cup, and the 2025-26 seasons of the five leagues. The result check pairs each stored cup and tournament match with one Wikipedia match box (`apply_boxes`), reading the season article and its sub-articles.

### Survey (2026-10-21)

Every page the verifier reads for a season with events was fetched and its line-up tables parsed. The openfootball events were paired with them by date and starting XI.

| Competition           | Stored matches with events |      Paired with a line-up table |
| --------------------- | -------------------------: | -------------------------------: |
| FIFA World Cup        |                      1,068 |                            1,068 |
| FIFA Club World Cup   |                        223 | 81 (all of 2025, earlier finals) |
| Five leagues, 2025-26 |                      1,752 |                                0 |

Table format:

- One unclassed table per match after the match box, holding two side tables. A side table has rows `position | number | player | cards | substitution`, then a `Substitutions:` header and the substitutes, then `Manager:`. Before 1950 there's no number column.
- Cards and substitutions are templates whose parameters are in the Parsoid HTML's `data-mw`: `{{yel|15}}`, `{{sent off|0|80}}` (red card), `{{sent off|2|54|74}}` (second yellow: first booking at 54, dismissal at 74), `{{suboff|72}}`, `{{subon|72}}`. `{{sentoff}}` is a spelling of `{{sent off}}`. Minutes may be `90+5`.
- The captain is marked `(c)` after the name.

Players, with three simple rules (normalised names equal, equal once spaces are removed, or a shared token): 30,611 of 30,793 paired (99.4%). The 182 failures are spelling variants: `Hans JEPPSSON` / Hans Jeppson, `Sepp HUEGI` / Sepp Hügi, `INDIO` / a full name.

Per side, comparing counts only:

| Item          | Same count | Different |
| ------------- | ---------: | --------: |
| Yellow cards  |      2,155 |       143 |
| Red cards     |      2,233 |        65 |
| Substitutions |      2,254 |        44 |

The differences seen were of three kinds:

- **Real errors.** Examples: openfootball has Luković (Serbia v Ghana 2010) booked once, while Wikipedia has him booked and then sent off; openfootball misses Rajković's booking in Serbia v Switzerland 2022.
- **Conventions.** In 1966, openfootball records cautions and Wikipedia doesn't. Wikipedia's second yellow is one `{{sent off|2|…}}`, where openfootball has a `YELLOW` and a `SECOND_YELLOW`.
- **Rounding.** Minutes differ by one (Žigić 18' / 19'), as Wikipedia often follows FIFA's rounding up.

## Goals / Non-Goals

**Goals:**

- Flag the matches whose line-ups, substitutions or cards disagree with Wikipedia, with a message precise enough to fix the source.
- No new requests, and no Wikipedia content stored or served.

**Non-Goals:**

- Unused substitutes, shirt numbers, positions and managers. They aren't stored (unused substitutes are option 3).
- Goals. Scorers are a separate check, if ever.
- Correcting the data. As with scores, a disagreement is reported and fixed upstream.
- League matches. Their articles have no line-ups.

## Decisions

### D1. Reference table

A match box's line-up table is the first table after it, before the next match box, that holds two side tables with a `GK` row. The parser returns, per side, the starters and the substitutes who came on (name, linked article title, number when there is one), the cards and the substitution minutes.

A box can appear twice: in the season article without a table, and in a sub-article with one. `merge_boxes` keeps the first box per match, which is the season article's. It changes to keep the first box's score but take the line-up table from whichever copy has one.

### D2. Events status

Computed for each stored match that the result check paired with a box:

| Stored events | Box has a table     | Status          |
| ------------- | ------------------- | --------------- |
| yes           | yes, all agree      | `VERIFIED`      |
| yes           | yes, any difference | `MISMATCH`      |
| yes           | no                  | `UNCONFIRMED`   |
| no            | yes                 | `SOURCE_BEHIND` |
| no            | no                  | none            |

A match with no paired box, or in a league, gets no events status. The comparison covers both sides:

1. starters, as sets of paired players;
1. substitutes who came on, as sets;
1. substitutions, as (player off, player on, minute);
1. cards, as (player, kind, minute), from 1970 on. Wikipedia's `{{sent off|2|a|b}}` counts as a `YELLOW` at `a` and a `SECOND_YELLOW` at `b`. `{{sent off|0|b}}` counts as a `RED` at `b`.

Minutes agree when they differ by at most one. The added minute is compared only when both sources have one.

### D3. Player pairing

Within one side of one match:

1. names normalised to lowercase ASCII words (accents folded, punctuation dropped, `(c)` removed) are equal, or equal once spaces are removed;
1. otherwise, a unique shared word;
1. otherwise, the same shirt number, when the stored player has one from the squad and the table has one.

A player left unpaired on either side is a difference. That makes a spelling variant a `MISMATCH`, which is what you want to hear about: one side should be corrected, or the pair added to the names already handled in `ingestion/openfootball/names.py`.

**Alternative:** pairing by Wikidata QID, from the player's linked article. Rejected for now: stored players have no QIDs, and adding them is its own change.

### D4. Storage

`match_verification` gains `aspect` (`RESULT`, `EVENTS`), and its unique key becomes (match, reference, aspect). That reuses the status enum, the cascade and `checked_at`, and keeps the result check's queries unchanged apart from a filter. A migration sets every existing row to `RESULT`.

`season_check` needs nothing new. Events are read from the same pages, so the stored revisions cover them, and events change only when the season is re-synced.

### D5. Report lines

One line per events `MISMATCH` or `SOURCE_BEHIND`:

```
WARNING FIFA World Cup 2010: MISMATCH events Serbia v Ghana: stored Luković Y 73', wikipedia Luković Y 54' 2Y 74'
```

For a skipped season, the line ends with `wikipedia unchanged since YYYY-MM-DD`, as for scores. The summary line gains the counts `events_VERIFIED=…` and so on. `tools/verify_report.py`'s disagreement pattern already matches the line; the key includes `events`, so result and events disagreements can't collide.

### D6. API

`events_verification` sits next to `verification` on match responses, with the same shape (`status`, `reference`, `checked_at`), and `null` when there is no status. `/v1/matches?events_verification=MISMATCH` filters on it.

## Open question

**Kuma.** The nightly report takes the monitor down for any `MISMATCH` not in `known-mismatches.txt`. With 150 to 200 events mismatches at first, the monitor would stay down until they're triaged. The options are:

1. **Recommended:** the report counts events mismatches but doesn't alert on them until a flag is turned on, after a first triage. The flag goes in the infra repo.
1. Add every first-run events mismatch to the known list on day one, and alert from then on.
1. Alert from day one.

## Expected first run

A full run re-verifies everything (the code changed), as after any deploy. Parsing adds seconds. Expect 150 to 200 events `MISMATCH`es, fewer once 1966-style cautions are excluded by the 1970 rule.

## Risks / Trade-offs

- **Table format drift.** A table the parser doesn't recognise makes a match `UNCONFIRMED`, not `MISMATCH`. The summary's `UNCONFIRMED` count shows when that happens.
- **Spelling variants show up as mismatches.** That's intended, but the first triage will be mostly that.
- **Stoppage time.** Old matches have only `90'`, recent ones `90+5'`. Comparing the added minute only when both sources have one avoids false mismatches, at the cost of missing an error in it.

## Also found

`parse_subarticle_titles` follows red links: the 1998 World Cup article links `1998 FIFA World Cup sponsorship?action=edit&redlink=1`, which costs a 404 on every verification of that season. The fix (skip `redlink=1` links) is a task in this change.
