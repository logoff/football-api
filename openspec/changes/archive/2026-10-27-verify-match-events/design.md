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

A box can appear twice: in the season article without a table, and in a sub-article with one. `merge_boxes` keeps the first box per match, which is the season article's. It changes to keep the first box's score but take the line-up table from the copy that records the most cards and substitutions: the 2010 knockout stage article repeats the final's line-ups without cards, which the final's own article has.

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
1. substitutions, as when each player went off and came on, only when the table records any substitution for the match;
1. cards, as (player, kind, minute), from 1970 on, only when the table records any card for the match. Wikipedia's `{{sent off|2|a|b}}` counts as a `YELLOW` at `a` and a `SECOND_YELLOW` at `b`. `{{sent off|0|b}}` counts as a `RED` at `b`.

Minutes agree when they differ by at most one. The added minute is compared only when both sources have one, and extra time written as added time (`90+8'`) agrees with the plain minute (`98'`).

Some tables list the players with no templates at all (the 2006 knockout article, some 1970s tables without `{{subon}}`). Treating them as "no cards" would flag every booking, so a table that records none says nothing about cards or substitutions.

### D3. Player pairing

Within one side of one match:

1. names normalised to lowercase ASCII words (accents folded, letters like `ı`, `ł` and `ø` mapped, punctuation dropped, `(c)` removed) are equal once spaces are removed, with German umlauts also tried as `ae`, `oe`, `ue` (`Hügi`, `HUEGI`);
1. otherwise, a unique shared word, ignoring particles such as `al`, `de` and `van`;
1. otherwise, the same shirt number, when the stored player has one from the squad and the table has one;
1. otherwise, the closest spelling: each word of the shorter name against its closest word in the other, averaged, at least 0.7, and each player the other's closest with no tie.

A player left unpaired on either side is a difference.

The last rule came from the integration run. Without it, about 270 starters per side stayed unpaired, nearly all transliterations sharing a common first name (`Yury ZHIRKOV` / `Yuri Zhirkov`, `AHMED HEGAZY` / `Ahmed Hegazi`, `Jose JOVEL` / `José Francisco Jovel`). With it, the rest are nicknames (`PAULO CESAR` / `Caju`) and genuinely different names, which the shirt numbers mostly resolve.

**Alternative:** pairing by Wikidata QID, from the player's linked article. Rejected for now: stored players have no QIDs, and adding them is its own change.

### D4. Storage

`match_verification` gains `aspect` (`RESULT`, `EVENTS`), and its unique key becomes (match, reference, aspect). That reuses the status enum, the cascade and `checked_at`, and keeps the result check's queries unchanged apart from a filter. A migration sets every existing row to `RESULT`.

`season_check` needs nothing new. Events are read from the same pages, so the stored revisions cover them, and events change only when the season is re-synced.

### D5. Report lines

One line per events `MISMATCH` or `SOURCE_BEHIND`, listing every difference by team and player:

```
WARNING FIFA World Cup 2010: MISMATCH events Serbia v Ghana: stored vs wikipedia: Serbia: Aleksandar Luković: cards Y 73' vs Y 54', 2Y 74'
```

For a skipped season, the line reads `…: stored events, wikipedia unchanged since YYYY-MM-DD`, as for scores. Each season with events statuses logs its own summary line, `…: events verified against wikipedia: VERIFIED=… MISMATCH=… UNCONFIRMED=… SOURCE_BEHIND=…`, so the results summary and the reports that read it are unchanged. `tools/verify_report.py`'s disagreement pattern already matches the line; the key includes `events`, so result and events disagreements can't collide.

### D6. API

`events_verification` sits next to `verification` on match responses, with the same shape (`status`, `reference`, `checked_at`), and `null` when there is no status. `/v1/matches?events_verification=MISMATCH` filters on it.

### D7. Kuma

The nightly report takes the monitor down for any `MISMATCH` not in `known-mismatches.txt`. With a couple of hundred events mismatches at first, the monitor would stay down until they're triaged. So the infra report counts events mismatches in its message but doesn't alert on them until a flag (`ALERT_EVENTS`) is turned on, after a first triage. Result mismatches alert as before.

The alternatives were listing every first-run events mismatch as known on day one, which hides them from review, or alerting from day one, which leaves the monitor down for weeks.

## Integration run

On an empty database with fresh sources, `--verify`, all 227 seasons:

| Run                         |        Time | Result                                                   |
| --------------------------- | ----------: | -------------------------------------------------------- |
| Full                        | 10 min 41 s | results unchanged (Boca v River the only mismatch)       |
| Second run, nothing changed |         9 s | same totals, the same 273 disagreements, nothing fetched |

Events statuses:

| Competition         | Verified | Mismatch | No table (`UNCONFIRMED`) |
| ------------------- | -------: | -------: | -----------------------: |
| FIFA World Cup      |      919 |      149 |                        0 |
| FIFA Club World Cup |       70 |       12 |                      141 |

The 161 events mismatches hold 124 card differences, 116 substitution minutes, 49 players only in Wikipedia's line-up (mostly the substitutes of two Club World Cup finals that openfootball doesn't record) and 25 pairs of names that don't match (`Szerfke` / `Scherfke`, `Sommers` / `Zomers`, nicknames).

A first run also gave `SOURCE_BEHIND` to every Euro, Copa América and Copa Libertadores match with a Wikipedia table. Those seasons record no line-ups at all, so a season whose `lineups` coverage is `none` now gets no events statuses, and loses any it had.

## Risks / Trade-offs

- **Table format drift.** A table the parser doesn't recognise makes a match `UNCONFIRMED`, not `MISMATCH`. The summary's `UNCONFIRMED` count shows when that happens.
- **Spelling variants show up as mismatches.** That's intended, but the first triage will be mostly that.
- **Stoppage time.** Old matches have only `90'`, recent ones `90+5'`. Comparing the added minute only when both sources have one avoids false mismatches, at the cost of missing an error in it.

## Also found

`parse_subarticle_titles` follows red links: the 1998 World Cup article links `1998 FIFA World Cup sponsorship?action=edit&redlink=1`, which costs a 404 on every verification of that season. The fix (skip `redlink=1` links) is a task in this change.
