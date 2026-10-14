# Design

## Context

League verification (`verification.py`) reads one results grid per season and pairs cells with stored LEAGUE matches by (home QID, away QID). Cups differ in three ways:

- **Layout:** each match is a separate box, in two templates rendered by Parsoid:
  - `table.tmpl-football-box-collapsible`: a date cell with a `dtstart` ISO date, two `vcard` club cells, and a score cell.
  - `table.fevent` ("Football box"): `.fhome`, `.fscore`, `.faway`, used mostly for finals.
- **Repeated pairings:** a pairing can occur more than once, as two legs (home and away swapped) or as a re-replay with the same home team (FA Cup 2023-24 Scarborough v Forest Green).
- **Result forms:** in the 32 articles, score cells take these forms:
  - `N–N`, optionally followed by `(a.e.t.)`, `(N–N agg.)` and/or `(N–N p)`.
  - `N–N (awd.)` or `N–N Awarded` for awarded results.
  - `Awarded`, `w/o`, `w/o (N–N)`, `Walkover`, `Void`, `Bye` or `v`, with no result to compare.

## Goals / Non-Goals

**Goals:** verify every cup season with the existing statuses and guarantees, reusing QID identification and the status table.

**Non-Goals:**

- UEFA and FIFA tournaments. Same templates, but different articles and group stages; a follow-up.
- Cup rounds openfootball doesn't have (FA Cup qualifying, Coupe de France rounds 1 to 6). Their boxes simply pair with nothing.

## Decisions

### D1. One box reader for both templates

`parse_match_boxes(html) -> list[MatchBox]`, where `MatchBox` holds the date, home title, away title, score `(h, a) | None`, shootout `(h, a) | None` and `awarded`.

- **Footnotes:** `<sup>` notes are removed first, as for grids.
- **Score grammar:** `^(\d+)–(\d+)` gives the score, `\((\d+)–(\d+) p\)` the shootout. `agg.` is ignored. `awd.` or `Awarded` sets `awarded`. Any cell that doesn't start with a score gives no score.
- **Football box dates:** `table.fevent` boxes carry their date in the preceding `.fdate` or `dtstart`. If a box has no date, it can still pair when its pairing is unique.

**Alternative:** parsing the wikitext templates (`{{Football box collapsible |team1=…}}`). Rejected for the same reason as D1 of the league change: the rendered HTML is uniform, while template parameters vary by article and age.

### D2. Pairing by QIDs, then by date

Group stored matches of the season (all stages) and boxes by (home QID, away QID).

- **One of each:** they pair.
- **Several:** boxes pair with stored matches of the same calendar date. A stored match's date is its `kickoff_utc` date, or the day before when a late-evening UK kickoff crosses midnight UTC. Those left over pair in date order.
- **Unpaired:** a stored match with no box gets no status, and the per-season summary counts them (`unpaired=N`).

**Alternative:** keying by round name. Rejected, because Wikipedia's section names (`Second round`, `Round of 32`) don't map one-to-one to our stages (`ROUND` 2, `R32`).

### D3. Comparison

The status rules stay as they are (`classify`), applied to the full-time score including extra time. When both the stored match (`decided_by=PENALTIES`) and the box have a shootout score, they must be equal for `VERIFIED`, otherwise it's `MISMATCH`. The level-awarded rule still applies. Disagreement lines show the shootout when there is one (`stored 1–1 (4–1 p), wikipedia 1–1 (4–2 p)`).

### D4. Dispatch by competition format

`verify_seasons` uses the grid reader for `LEAGUE` and the box reader for `CUP` and `LEAGUE_CUP`. `ResultsReference` gains `match_boxes(title)`. The run lock, error handling (`WikipediaUnavailable`, no boxes means statuses unchanged) and logging are shared.

## Source coverage

**Verified run of the six cups** (empty database, 48 s):

| Cup             | Seasons | VERIFIED | MISMATCH | UNCONFIRMED | Unpaired |
| --------------- | ------- | -------- | -------- | ----------- | -------- |
| FA Cup          | 7       | 967      | 8        | 1           | 5        |
| EFL Cup         | 7       | 645      | 0        | 0           | 1        |
| Copa del Rey    | 5       | 589      | 4        | 0           | 38       |
| DFB-Pokal       | 7       | 417      | 0        | 0           | 24       |
| Coppa Italia    | 5       | 248      | 0        | 0           | 11       |
| Coupe de France | 1       | 107      | 1        | 1           | 91       |

Unpaired matches involve clubs without a Wikidata QID, or without a linked article in the box (mostly amateur clubs). Their boxes can't be identified.

**Mismatch review.** Each of the 13 was checked against a third source: club reports, ESPN, or the national press.

- **English Wikipedia errors (8, FA Cup):**

  - Bury 0–1 Luton (2018-19)
  - Shrewsbury 1–0 Scunthorpe (2018-19)
  - Southend 2–4 Barnsley (2018-19)
  - Bradford v Peterborough, 4–4 and 2–3 on penalties (2018-19; Peterborough's own report)
  - Bristol City 0–1 Fulham a.e.t. (2021-22)
  - Coventry 1–0 Derby (2021-22)
  - Mansfield 2–3 Middlesbrough (2021-22)
  - Sheffield Wednesday 2–0 Morecambe (2022-23)

  openfootball is right in all eight.

- **openfootball errors (5):**

  - Calahorra v Atlético Baleares, 1–1 and 4–5 on penalties (Copa del Rey 2021-22). The source writes `4-5`.
  - Guijuelo v Rayo Vallecano, 1–1 and 3–4 on penalties (2021-22). The source has `0-0`.
  - Ourense v Alcorcón, 1–1 and 2–4 on penalties (2022-23). The source writes `2-4`.
  - Azuaga v Cartagena, 0–0 and 2–3 on penalties (2023-24). The source has `2-3 a.e.t.`.
  - AS Dragon v Avranches, 2–2 and 4–3 on penalties (Coupe de France 2024-25). The source has `4-2 pen.`.

  Wikipedia is right in all five. Stored scores stay as the source has them, and the errors are for reporting upstream.

- **Seed fix found by the run:** Q2310972 is CD Guijuelo, but its English Wikidata label reads "CD Albacete", and the team had been named after it. It's renamed "CD Guijuelo".

## Risks / Trade-offs

- **[Risk] Many amateur clubs without a QID.** 64 cup clubs have none, so their boxes can't pair. → Those matches get no status. The existing per-team warning names them, and the summary counts them as unpaired.
- **[Risk] Midnight-UTC date shifts break date pairing.** → Date pairing allows a one-day difference (D2), and only matters for repeated pairings.
- **[Trade-off] Wikipedia lists games openfootball omits**, such as voided replays and walkovers. → Unpaired boxes are ignored.

## Migration Plan

No schema change. After deploy, a verified cup run (`--competition` with the cup QIDs and `--verify`) writes the statuses.
