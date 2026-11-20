# Proposal

## Why

Two World Cup rounds are stored as finals, because the stage rules match the word "final":

- **1950, `Final Round`:** the four-team round robin that decided the title (Uruguay, Brazil, Sweden, Spain) is six `FINAL` matches. It has no table, and the six matches show up wherever a client asks for finals. `euro-and-copa-america-from-wikipedia` left it out of scope.
- **2026, `Bronze final`:** FIFA's name for the third-place match, France v England, is stored as `FINAL`, next to the real final.

A check of every openfootball label stored as `FINAL` finds no others: the rest are `Final`, `Finals, Final` and `Final, Replay`.

## What Changes

- **`Bronze final` is a third-place match:** the third-place stage rule also matches `bronze`. No other stored label contains it.
- **`wikipedia_rounds` becomes `rounds`, for every season:**
  - An openfootball season can now rename a heading of its round labels too. 1950 gets `rounds: {Final Round: Second group stage}`, so its final round is `GROUP` in phase 2, with a table. That's how the 1989 and 1991 Copa América final groups are stored.
  - A listed heading no match has fails the season, as for Wikipedia seasons.
  - A season read from results grids rejects the field, since it has no headings to rename.
  - The 31 Copa América seasons that use it are renamed in the seed. Wikipedia seasons read it as before.
- **Not changed:** "Final round" keeps mapping to `FINAL` in the stage rules. Other sources use it for knockout finals, so the season says what it means (`euro-and-copa-america-from-wikipedia` D3).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ingestion`: the renamed `rounds` field applies to openfootball seasons too, and `Bronze final` maps to `THIRD_PLACE`.

## Impact

- **Code:** the seed model, the stage rules in `text_parser.py`, the Wikipedia reader, and the openfootball read path in `sync.py`.
- **Seeds:** `rounds` on the 1950 World Cup, and the field renamed on 31 Copa América seasons.
- **Data:** 1950's six final-round matches move from `FINAL` to `GROUP`, and the 2026 third-place match from `FINAL` to `THIRD_PLACE`. Sync keeps their identity when a stage changes. The 1950 final round gets a table, checked against Wikipedia's like every 1950 table.
- **API:** a client filtering on `stage=FINAL` no longer gets those seven matches.
