# Design

## Context

A survey parsed every international season file openfootball has with the current code.

- **Parse as they are:** the UEFA club competitions, Copa Libertadores, Club World Cup and World Cup files. Some round labels are missing stage rules: `Gruppe G` (2020-21 to 2023-24 UEFA files), `Gruppe 1` (Libertadores 2012 to 2022), `1st Round`, `2nd Round`, `First round` and `Second round` (Club World Cup, World Cup 1938), and `Match for fifth place` / `5th Place` (Club World Cup).

- **Don't parse yet:** the Euro files before 2024 and the Copa América files before 2024. They mix five date styles:

  - a `July 6` line before timed matches (1960–1968);
  - a `June 14 20:00 @ Venue` block line before the match (1972–1984);
  - `June 10 @ City  Home 1-1 Away`, with date, venue and match on one line (1988, 1996);
  - `June 12 18:00 @ City Home 1-1 Away` (2000, 2004);
  - `Jul 1  21:45   Argentina  1-1  Bolivia` (Copa América 2011, 2021).

  Euro 1992's group matches have no dates at all.

- **Kickoff times:**

  - The World Cup and Club World Cup files carry a `UTC±N` offset on every timed line (`tz: inline`).
  - The UEFA files give Central European times (`Europe/Berlin`, as for 2024-25).
  - The Libertadores files give Brasília times (`America/Sao_Paulo`, as for 2025).
  - The old Euro files state their zone in a header comment (`All times are local, CET (UTC+1)`).

## Goals / Non-Goals

**Goals:**

- Ingest every edition with a date for every match.
- Read every layout above without changing how existing files parse.

**Non-Goals:**

- Wikipedia verification. A follow-up change needs several articles per season (group stage, knockout phase).
- Qualifying rounds (`clq.txt` and similar).
- Squads beyond the editions that have them today.
- Inventing dates for undated matches.

## Decisions

### D1. Dates without a weekday

The date-marker pattern accepts `<Month> <day>` with a full or three-letter English month name, an optional year, and an optional leading weekday. The year comes from the file's start year, rolling over when months go backwards, as for weekday dates today.

A date may also prefix a match line. The parser then reads the rest of the line as `[time] [@ venue] match`, using the existing time, venue and match parsing. That covers all five styles with one rule.

**Alternative:** one parser per file layout. Rejected, because the layouts differ only in what precedes the match.

### D2. Undated editions are left out

A match needs a kickoff date (`kickoff_utc` is NOT NULL). If an edition's file has a match without any date in scope, parsing fails for that edition, and that edition isn't seeded. Euro 1992 is the known case. Each excluded edition is listed in the README.

**Alternatives:**

- **Placeholder dates.** Rejected: invented data.
- **A nullable kickoff.** Rejected for this change: it would ripple through the API and ordering.

### D3. Stage rules

- `Gruppe` joins `group` → `GROUP`.
- `1st|2nd|…` / `First|Second|…` + `Round` → `ROUND` N.
- `fifth place|5th place` → new `FIFTH_PLACE`.
- Existing labels keep their stages. A test runs every seeded file and asserts that every label maps.

### D4. Time zones

- World Cup and Club World Cup: `inline`.
- UEFA: `Europe/Berlin`.
- Libertadores: `America/Sao_Paulo`.
- Each older Euro and Copa América edition: a fixed `Etc/GMT±N` zone taken from its header comment (for example `Etc/GMT-2` for "CEST (UTC+2)"), because those files state a fixed offset, not a region.
- Each choice is checked against a few known kickoffs.

### D5. Teams

As for the cups: draft with `tools/propose_teams.py`, then verify every QID's instance-of and country, and review labels that barely overlap the spelling.

Historic national teams follow Wikidata: the Soviet Union and Russia, Yugoslavia and Serbia and Montenegro, Czechoslovakia and the Czech Republic, and East Germany are separate items. West Germany is not: Wikidata lists it as an alias of the Germany team (Q43310), in line with FIFA, so its matches belong to Germany and "West Germany" stays as the openfootball spelling. Historic states get no country, since they have no current ISO 3166-1 code. A label that disagrees with the spelling (the CD Guijuelo case) is caught by the label-overlap check and named from the spelling.

## Source coverage

**More parser findings during implementation.** All are handled, with tests, and none changed how an existing file parses:

- Kick-by-kick `Penalties:` blocks (Euro 1976 and 1980, Club World Cup) were being read as matches.
- Shoot-outs and extra time written after the away team: `(9-8 pen)`, `(aet, 6-5 pen)`, `(aet/gg)`, `(aet/sg)`.
- `(19:00 EEST)` local-time notes, and `15:00 (17:00 UTC+4)` local times with an offset.
- German knockout labels (`Sechzehntelfinale`).
- `N.N.` placeholder fixtures in Copa Libertadores 2026, which are skipped.

**Time zones.**

- UEFA: the 2012 Champions League final is listed 20:45 and kicked off at 20:45 CEST, so `Europe/Berlin` is right.
- Copa Libertadores: the files use Brasília time, even for matches played elsewhere. The 2019 final in Lima (15:00 local) is listed 17:00, and the 2025 final (18:00 Brasília, 17:00 Lima) is listed 18:15. So `America/Sao_Paulo` is right.
- World Cup, Club World Cup and Copa América 2021/2024: an explicit offset on every line.
- Euro 1960–2021: the fixed offset stated in each file's header. Euro 2021's matches in other zones carry their own offset.
- Copa América 2011: Argentina's time.

**Teams.**

- 387 missing spellings: 128 became aliases of seeded teams and 245 are new teams.
- Every new QID was checked for instance of and country, plus label overlap with the spelling. 52 the draft couldn't match were resolved by hand (Boca Juniors, Peñarol, Sydney FC…).

**Integration run** (empty database, two syncs, 2 min 24 s each):

- 44,928 matches, and the second run is byte-identical.

- All 227 seasons match their files' match counts, and the 134 seasons that existed before are unchanged.

- By competition:

  | Competition            | Editions | Matches                |
  | ---------------------- | -------- | ---------------------- |
  | UEFA Champions League  | 15       | 1,997                  |
  | UEFA Europa League     | 5        | 817                    |
  | UEFA Conference League | 4        | 576                    |
  | Copa Libertadores      | 15       | 2,229                  |
  | FIFA Club World Cup    | 21       | 224 (16 `FIFTH_PLACE`) |
  | FIFA World Cup         | 23       | 1,068                  |
  | UEFA Euro              | 15       | 358                    |
  | Copa América           | 3        | 86                     |

## Risks / Trade-offs

- **[Risk] The new date rule changes how existing files parse.** → Every currently seeded file is parsed before and after the change, and the match lists must be identical.
- **[Risk] Historic national teams resolve to the wrong Wikidata item.** → Manual review against the edition (for example, a 1976 "West Germany" must be the West Germany national team item).
- **[Trade-off] Undated editions are missing.** → Listed in the README and added if the source gains dates.

## Migration Plan

One Alembic revision adds `FIFTH_PLACE` to `stage`. The downgrade rebuilds the type and fails if any match uses it. The first sync after deploy loads the history.
