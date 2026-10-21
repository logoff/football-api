# Proposal

## Why

Scores are checked against Wikipedia, but line-ups, substitutions and cards aren't checked against anything. They come from one source, openfootball's `-full` files, which are typed by hand. A survey on 2026-10-21 found real disagreements: openfootball records Aleksandar Luković's 2010 dismissal as a single yellow card, and misses Predrag Rajković's booking in Serbia v Switzerland 2022.

The pages to check against are already fetched. The World Cup group and knockout articles have a line-up table after every match box. The table lists the starters, the substitutes who came on, and templates for bookings (`{{yel}}`), dismissals (`{{sent off}}`) and substitutions (`{{suboff}}`, `{{subon}}`).

## What Changes

- **A second status per match, for its events.** A match whose stored events can be compared gets an events status, alongside its result status: `VERIFIED`, `MISMATCH`, `UNCONFIRMED` (the match box has no line-up table) or `SOURCE_BEHIND` (only Wikipedia has line-ups). One status covers the whole match: starters, substitutes who came on, substitutions and cards, on both sides.
- **The reference is the line-up table after the match box** that the result check already pairs with the match. No new pages are fetched, so the revision checks from `skip-unchanged-seasons` already cover it.
- **Players are paired within a side by name.** The comparison ignores case, accents and punctuation. Shirt numbers are used where names fail. Cards and substitutions then compare by paired player, kind and minute, allowing one minute's difference.
- **Cards are compared from 1970 on**, the first World Cup with cards. Before that, line-ups and substitutions are still compared.
- **Disagreements are logged** one line per match, naming each difference, in the format the reports already read.
- **API:** match responses gain `events_verification`, shaped like `verification`, and `/v1/matches` accepts an `events_verification` filter.

Scope follows the data. Of the matches with stored events, Wikipedia has a line-up table for all 1,068 World Cup matches and 81 Club World Cup matches: all of 2025, and the finals and some third-place matches of earlier editions. The five league articles have no match boxes, so their 2025-26 matches get no events status.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `match-verification`: new requirements Reference line-ups, Events status per match, Events comparison, Player pairing, Events disagreement report, and Events verification in the API.

## Impact

- **Code:** `ingestion/wikipedia.py` (parse line-up tables next to match boxes), `verification.py` (compare events, store and report the status), API schemas and the matches filter.
- **Database:** `match_verification` gains an `aspect` column (`RESULT` or `EVENTS`), and the unique key becomes (match, reference, aspect). Existing rows become `RESULT`. Migration required.
- **API:** additive. `verification` keeps its meaning.
- **Cost:** no new requests. Parsing about 1,150 line-up tables adds seconds to a full run.
- **Reports:** expect 150 to 200 matches marked `MISMATCH` on the first run. Some will be real errors to fix upstream, some differences in convention. Until they're triaged, they shouldn't take the Kuma monitor down (see the design's open question).
