# Design

## Context

The cup reader (`parse_match_boxes`) and the pairing (`apply_boxes`) already handle knockout boxes, extra time, shoot-outs and awarded results.

A survey of one or two seasons per international competition found the following:

- **UEFA club competitions:** the season article has almost no boxes. They sit in `… group stage` / `… league phase` and `… knockout phase`.
- **Copa Libertadores:** `… group stage` / `second stage` and `… final stages` / `knockout stages`.
- **World Cup, Euro and Club World Cup:** the main article usually has every match, and the group sub-articles repeat them.
- **Noise:** linked sub-articles also include separate qualification tournaments, squads, women's and futsal editions, and `final`/`Final` redirect duplicates.

With the right sub-articles, box counts match ours. For example, the 2011–12 Champions League has 96 group-stage + 29 knockout boxes = 125 matches.

## Goals / Non-Goals

**Goals:** verify every international edition with the same statuses and guarantees as the cups, with a bounded number of requests.

**Non-Goals:**

- Qualifying rounds that openfootball doesn't publish (UEFA): their boxes stay unpaired.
- Squads or line-ups.

## Decisions

### D1. Sub-article discovery by title prefix

From the season article's rendered HTML, take every internal link whose target title starts with the season title plus a space, after resolving the `./` href.

Qualifying sub-articles (`qualif…`) are read only when the season stores qualifying matches (stage `QUALIFYING`, `PRELIMINARY` or `ROUND`), as the Copa Libertadores does with its `qualifying stages`. Otherwise they are separate tournaments (`UEFA Euro 2024 qualifying`, `2026 FIFA World Cup qualification`) or rounds openfootball doesn't publish (UEFA club qualifying). Always exclude a sub-article when its suffix matches `qualification`, `squad`, `femenin`, `futsal`, `bid`, `statistic`, `broadcast`, `official`, `controvers`, `seeding`, `ceremony`, `disciplin` or `record`.

The sub-articles are fetched once each, in link order, with the existing polite client (User-Agent, timeout, one retry).

**Alternative:** listing every sub-article in the seeds. Rejected: it would mean hundreds of titles to maintain by hand, and they change as editors split or merge articles.

### D2. De-duplication

Boxes are keyed by (date, home title, away title). The first occurrence wins, and the season article is read first. This covers both main article plus group article and `final`/`Final` redirects.

### D3. Dispatch

`verify_seasons` uses the box reader with sub-articles for `CUP`, `LEAGUE_CUP` and `TOURNAMENT`. Domestic cup articles have no qualifying-style sub-articles, so their behaviour doesn't change.

### D4. Titles

The seeds name the actual season article:

- `YYYY–YY UEFA Champions League` and `YYYY–YY UEFA Europa League`.
- `YYYY–YY UEFA Europa Conference League` up to 2023-24, then `2024–25 UEFA Conference League`.
- `YYYY Copa Libertadores`.
- `YYYY FIFA Club World Championship` for 2000 and 2005, then `YYYY FIFA Club World Cup`.
- `YYYY FIFA World Cup`.
- `1960 European Nations' Cup` and `1964 European Nations' Cup`, then `UEFA Euro YYYY`, with `UEFA Euro 2020` for the 2021 edition.
- `YYYY Copa América`.

Every title is checked to resolve before seeding.

## Risks / Trade-offs

- **[Risk] A non-match sub-article slips through the exclusions and adds unrelated boxes.** → Unpaired boxes are ignored, and pairing is by QIDs and date, so a stray box can only pair if it's the same fixture on the same day.
- **[Risk] Request volume.** → About 600 requests for all tournaments. That's acceptable for manual or occasional runs. The nightly job verifies only what it syncs.

### D5. Teams named the other way round

At neutral venues openfootball and Wikipedia sometimes order the teams differently, for example `Yugoslavia v Argentina` against `Argentina v Yugoslavia` at the 1990 World Cup. After the usual pairing, a stored match left over pairs with the single unused box of the reversed pairing within a day of its date. That box's score and shoot-out are flipped before comparing. Two-legged ties are unaffected: both legs exist in both orientations and pair in the first pass.
