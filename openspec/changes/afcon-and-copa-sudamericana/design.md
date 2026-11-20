# Design

## Context

- **openfootball/south-america** has `<year>_copas.txt` next to the Libertadores files. The Libertadores is already read from them (`America/Sao_Paulo` times).
  - **2012–2020:** numbered rounds (`ROUND`), then round of 16 to the final.
  - **2021–2024:** a preliminary stage, eight groups of four, round of 16 to the final. 2023 and 2024 add knockout play-offs.
  - **2016:** the final is marked `[cancelled]` in both legs, and reads as `CANCELLED`.
  - **2025:** the file stops in the group stage.
- **The spike, run on 2026-11-20 with the match-box reader over AFCON 1957–2025 and Sudamericana 2002–2011, 2025 and 2026:**
  - **AFCON:** every edition reads. Every box has a date, and every team article has a QID. Headings to handle:
    - **1959:** three matches under `Final tournament`, a round robin of three.
    - **1976:** `Final round`, a round robin of four after two groups.
    - **1963:** the sub-article `… Final` holds the whole tournament, so its boxes are labelled `Final / Group stage / Group A`.
    - **2002:** the final appears twice, once under `Final / Match details / Details`.
    - **No score:** 1957 Ethiopia v South Africa (disqualified) and 2010 Togo's three group matches (withdrawn).
  - **Sudamericana 2025:**
    - `First stage` names no stage.
    - `Final stages / Knockout round play-offs` maps to `FINAL` because of `Final stages`.
  - **Sudamericana 2002–2011:** 2 to 76 boxes per edition, mostly finals. The articles use bracket tables for the rest.
  - **Sudamericana 2026:** one match still without a score.

## Goals / Non-Goals

**Goals:**

- AFCON from 1957 and the Copa Sudamericana from 2012, with the same fields as the competitions already served.
- Group tables with ranking rules checked against Wikipedia's.

**Non-Goals:**

- **Qualifying** for AFCON, as for every tournament.
- **Sudamericana 2002–2011.** They could come later from another source or from results tables, which would be a new reader.
- **Sudamericana 2026** until openfootball publishes it.

## Decisions

### D1. Copa Sudamericana

- **2012–2024 from openfootball,** with `tz: America/Sao_Paulo` as for the Libertadores, and `wikipedia: "<year> Copa Sudamericana"` for verification.
- **2025 from Wikipedia,** pinned, with `rounds: {First stage: Preliminary round}`, which matches the `PRELIMINARY` stage of 2021–2024.
  - **Alternative: wait for openfootball 2025.** Rejected. The edition finished a year ago and the file has stopped.
- **When openfootball completes 2025,** the season can move to it, as any Wikipedia season can.

### D2. `Final stages` is a wrapper

- `final stages` joins the wrapper headings in `_NOT_A_STAGE`, next to `final phase` (`cup-winners-cup-and-uefa-cup-from-wikipedia` D2).
- **Check:** sync every Wikipedia season before and after, and compare stages. Only Sudamericana 2025's knockout play-offs should be affected.

### D3. Africa Cup of Nations

- **Labels:** the edition's year as CAF names it (`2021`, `2023`, `2025`). `start_year` is the year of the first match: 2022 for the 2021 edition, 2024 for 2023, 2025 for 2025.
  - **Alternative: label by the year played, as Euro 2020's `2021`.** Rejected. That label comes from openfootball's file. Here there is no file, and CAF, FIFA and Wikipedia use the edition name.
- **Round robins:** `rounds: {Final tournament: Group stage}` for 1959, and `rounds: {Final round: Second group stage}` for 1976.
- **1963:** the `… Final` sub-article is left out of the pins, so its copies of the tournament aren't read. The main article's boxes are used, and if they're missing, `wikipedia_skip` names the sections instead. Settled while pinning, with the box count as the check.
- **2002:** the duplicate final is found while pinning: a different date or side order. It's resolved by leaving out that section or pin.
- **Not played:** boxes without a score are already `CANCELLED` (`source-older-seasons-from-wikipedia` D4).

### D4. Teams

- **National teams:** the 30 missing African teams are added by QID, named by the country rule in `teams.yaml`.
- **Clubs:** drafted with `tools/propose_teams.py` from the openfootball spellings, and from the 2025 Wikipedia QIDs, then reviewed. A club already seeded from the Libertadores gains its Sudamericana spelling.

### D5. Ranking rules

- **AFCON:** two points for a win until the edition that changed it, then three. The tie-breakers of each era are taken from the regulations as Wikipedia quotes them.
- **Copa Sudamericana:** eras from 2012 (no groups until 2021) and 2021, following the Libertadores where the regulations agree.
- **Check:** every computed group table of the new Wikipedia seasons is compared once with Wikipedia's, without storing anything. The openfootball seasons get their usual standings verification.

### D6. Delivery

- **Three PRs:** this proposal, then the Copa Sudamericana with D2, then AFCON.

## Risks / Trade-offs

- **Wikipedia errors become AFCON's data** → the same accepted risk as for the European Cup. The group-table check catches score errors in group matches.
- **Early AFCON formats differ edition by edition** → each pin is read, and its box count and stages are checked against the article before it's seeded.
- **Many new clubs** → drafting with the existing tool and reviewing by country, as for the Cup Winners' Cup's 319 clubs.
