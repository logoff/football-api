# Design

## Context

- **How Wikipedia seasons are read:** a Wikipedia season is read from the match boxes of its pinned revisions by `wikipedia_season.read_season` (`source-older-seasons-from-wikipedia`).
  - The stage comes from the box's heading path. `round_label` drops wrapper headings listed in `_NOT_A_STAGE`, then `normalize_stage` maps what's left.
  - Clubs resolve by the QID of the article each box links, cached next to the revision.
- **The spike, run on 2026-11-18 with that reader over every season:**
  - **Cup Winners' Cup:** 39 seasons and 2,296 boxes. The articles are titled `European Cup Winners' Cup` until 1993-94 and `UEFA Cup Winners' Cup` from 1994-95. Each season is one article.
  - **UEFA Cup and Europa League:** 48 of 49 seasons read, with 8,054 boxes. From 1999-2000 the UEFA Cup splits into round sub-articles (`first round`, `second round`, `group stage`, `final phase`, `knockout stage`), and the Europa League into `group stage` and `knockout phase`. Discovery finds them all, and no qualifying sub-article is pulled in.
  - **1996–97 UEFA Cup** fails: a box links `Khazri Buzovna`, a red link with no QID. The club is Q2338519 on Wikidata.
  - **Dates and results:** every box has a date.
    - Boxes with no result: 4 walkovers in 1971-72 (Rapid Wien v Vllaznia twice, PSV v Hallescher, Panionios v Ferencváros), 2 in 1972-73 (Hvidovre v HIFK), and 3 in the 2004-05 and 2006-07 groups.
    - Awarded boxes: Hajduk Split v Marseille 1987-88 (Cup Winners' Cup), Fiorentina v Grasshopper 1998-99, Celta v Red Star 2000-01 and Rapid București v Paris Saint-Germain 2001-02.
  - **`Final phase` wrapper:** the UEFA Cup's `Final phase / Third round`, `/ Fourth round`, `/ Round of 32` and so on mapped to `FINAL`, because `normalize_stage` finds `final` in the label. 302 boxes were labelled `FINAL` instead of 37 finals. The same goes for the Cup Winners' Cup's `Tournament phase` and `Qualifying phase` in 1960-61 and 1961-62.
  - **Qualifying rounds:** they appear in the main articles in 22 seasons. The Cup Winners' Cup has `Preliminary round` from 1962-63 and `Qualifying round` from 1990-91. The UEFA Cup has `Preliminary round` in 1989-90, 1994-95 and 1995-96, and `First/Second qualifying round` in 1997-98 and 1998-99.
  - **Clubs:** 357 aren't seeded yet.
  - **No stored data changes:** no stored round label contains `Final phase`, `Tournament phase` or `Qualifying phase`, so the wrapper fix changes nothing already stored.

## Goals / Non-Goals

**Goals:**

- Every Cup Winners' Cup season, and every UEFA Cup and Europa League season before openfootball's, with the same scope and fields as the Champions League from Wikipedia: date, stage, teams, score, shootout and the awarded flag.
- Group tables for the UEFA Cup and Europa League group stages, with rules checked against Wikipedia's tables.

**Non-Goals:**

- **The Inter-Cities Fairs Cup (1955-71).** UEFA doesn't count it as one of its competitions. If it's ever added, it would be its own competition.
- **The UEFA Intertoto Cup and the qualifying rounds from 1994-95**, as for the Champions League.
- **Scorers, line-ups and venues from the boxes**, as in `source-older-seasons-from-wikipedia`.
- **Verifying these seasons.** Wikipedia is their source, so it can't also be their check. A one-off cross-check, like La Liga's with RSSSF, can follow if the group-table comparison suggests errors.

## Decisions

### D1. Competitions and seasons

- **Cup Winners' Cup:** a new competition, `UEFA Cup Winners' Cup`, with `CLUB`, `CONTINENTAL`, `TOURNAMENT`, Q40241 and no country.
  - **Alternative: `CUP`.** Rejected. `CUP` means a knockout open to a national pyramid. The European Cup was a knockout until 1991-92 and is `TOURNAMENT`.
- **UEFA Cup:** its seasons join the existing `UEFA Europa League` (Q18760) as 1971-72 to 2019-20, labelled like the Champions League's (`1999-00`). The competition keeps its current name, as the Champions League does for the European Cup years. Each season's `source` names the article it was read from.
- **Pins:** by `just wikipedia-pins`, one block per season, exactly as for the Champions League.

### D2. Wrapper headings

- **The fix:** `Final phase`, `Tournament phase` and `Qualifying phase` join `_NOT_A_STAGE` in `wikipedia_season.py`.
  - `Final phase / Third round` becomes `Third round`, which is `ROUND` 3.
  - `Tournament phase / Semi-finals` becomes `Semi-finals`.
  - The 1960-61 `Qualifying phase / Preliminary round` becomes `Preliminary round`, which is `PRELIMINARY`. That's what it was: the first round of a competition that had no separate qualifying.
- **Alternative: special-case the `final` rule in `normalize_stage`.** Rejected. These headings group rounds and are never a round themselves, and `_NOT_A_STAGE` is where that is already said.

### D3. `wikipedia_skip`

- **The field:** an optional season field, `wikipedia_skip: [<heading>, …]`, valid only with `wikipedia_source`.
  - The reader drops every box whose heading path contains a listed heading. Matching is case-insensitive and on the whole heading.
  - A listed heading that none of the pinned pages has fails the season. A moved pin whose article renamed `Qualifying round` would otherwise start storing that round without anyone noticing.
- **Where it's used:** it leaves out the qualifying and preliminary rounds from 1994-95, the year the Champions League's scope changes (proposal). The spike puts 154 Cup Winners' Cup boxes and 278 UEFA Cup boxes in those rounds.
- **Alternative: skip by stage (`QUALIFYING`, `PRELIMINARY`).** Rejected. `PRELIMINARY` before 1994-95 is the competition proper, so a stage rule would need years attached. Headings are what the reviewer sees in the article.
- **Alternative: leave qualifying in everywhere.** Rejected. It's inconsistent with the Champions League and with openfootball's Europa League from 2020-21, which starts at the group stage.

### D4. `wikipedia_qids`

- **The field:** an optional season field, `wikipedia_qids: {<linked title>: <QID>}`, for a box that links an article which doesn't exist.
  - The reader checks it before the title → QID lookup, and doesn't cache the result next to the revision, since the seed is already the record.
  - An entry for a title no box links fails the season, as stale `wikipedia_skip` entries do.
- **First use:** `1996–97 UEFA Cup`, with `Khazri Buzovna: Q2338519`.
- **Alternative: edit Wikipedia to create or relink the article.** Rejected for now. It depends on someone else's edit, and the club's identity is clear on Wikidata.

### D5. Fingerprint

`wikipedia_skip` and `wikipedia_qids` are left out of the season dump while unset, as `wikipedia_grids` is. Adding them doesn't change any existing season's fingerprint.

### D6. Teams

The 357 clubs are generated from Wikidata, with name, country (P17) and `kind: CLUB`, and reviewed by hand, as in `source-older-seasons-from-wikipedia` D5. Clubs whose QID Wikipedia links for an older incarnation keep that QID unless the Champions League seasons already fold it under `reference_wikidata`.

### D7. Walkovers and awarded matches

- **Walkovers:** a box with no result is `CANCELLED` without a score, as in the Champions League.
- **Awarded boxes:** the four get `seeds/awarded.yaml` entries, each with its `played` value confirmed from a source.

### D8. Group-stage ranking rules

The Europa League gets standings eras for its group stages:

- **2004-05 to 2008-09:** the UEFA Cup's eight groups of five, each team playing four matches, two at home. These are the single-round groups `standings.py` already handles.
- **2009-10 to 2019-20:** twelve groups of four, home and away, under the Champions League's regulations of the same years.
- **How the eras are fixed:** points are 3-1-0 throughout, and the tie-breakers are cited from UEFA's regulations as Wikipedia quotes them. Every computed group table is compared once with Wikipedia's, without storing anything, as was done for the Champions League (142 of 142) and La Liga. The PR states the result and explains any difference.

### D9. Delivery

- **Two PRs:** the code (D2–D5, with tests), then the seasons, teams, eras and docs (D1, D6–D8).
- **Size:** the data PR is large, about 88 pin blocks and 357 teams, but it's reviewed the way #56 was.

## Risks / Trade-offs

- **Wikipedia errors become our data** → the same accepted risk as for the Champions League and La Liga. The group-table comparison catches score errors in the group stages. Knockout errors would need a cross-check like La Liga's, which is left as a follow-up.
- **Team identity across eras** → the seeded QID is the one Wikipedia links. Old Eastern European clubs and renamed clubs may appear as separate teams where Wikidata separates them. That's consistent with the Champions League seasons, which share most of these clubs.
- **Size** → about 9,900 more matches and 357 teams. Sync time grows by about 160 cached revisions on the first run.
