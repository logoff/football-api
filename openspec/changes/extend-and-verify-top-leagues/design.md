# Design

## Context

`verify-and-schedule-la-liga` built everything this change needs: the `seasons:` list in the seeds, the Wikipedia grid reader, the per-match verification statuses, and the competition-scoped `--verify` sync. This change is mostly seed data. An investigation before writing it found:

- **Parser:** all 71 league text files parse to the expected match counts with the current parser. That is 380 matches for a 20-club season and 306 for an 18-club one.
- **Wikipedia:** 70 of the 71 season articles had a grid the reader detects, with as many scores as openfootball has played matches. Serie A 2018-19's table had no links in its rows or column headers, until the clubs were linked in the article (D2).
- **Teams:** about 150 openfootball team spellings across the four leagues are not in `seeds/teams.yaml`.

## Goals / Non-Goals

**Goals:**

- Ingest and verify the four leagues' full openfootball history with no parser or verifier code changes.
- Keep team identity QID-based and hand-reviewed, as for La Liga.

**Non-Goals:**

- Cups and tournaments, which need a different Wikipedia reader (see proposal.md).
- Lineups and events from Ligue 1's `-full` files, which belong to `add-match-events`.

## Decisions

### D1. Seeds per season

Each league gets one `seasons:` entry per season, in the same shape as La Liga:

| League         | `file`                                 | `tz`            |
| -------------- | -------------------------------------- | --------------- |
| Premier League | `england/<label>/1-premierleague.txt`  | `Europe/London` |
| Bundesliga     | `deutschland/<label>/1-bundesliga.txt` | `Europe/Berlin` |
| Serie A        | `italy/<label>/1-seriea.txt`           | `Europe/Rome`   |
| Ligue 1        | `europe/france/<label>_fr1.txt`        | `Europe/Paris`  |

- **`json`** is set wherever `football.json/<label>/{en,de,it,fr}.1.json` exists, which is every season from 2010-11 onwards. The Premier League's 2000-01 to 2009-10 seasons are text only. The mirror is still used only when it's current, so leaving it out changes nothing.
- **`wikipedia`** is the article's actual title, not a redirect. For the Premier League that means `YYYY–YY FA Premier League` up to 2006-07 and `YYYY–YY Premier League` after. The reader already follows redirects, so a renamed article keeps working until the seed is updated.
- **Alternative considered:** generating the season list from the source tree at sync time. Rejected, because the seeds are the reviewed contract for what is in scope and what verifies it, and a new season should be a reviewed one-line change.

### D2. Serie A 2018-19: links added in the article

The article's results table named its clubs without links ("Milan", "Roma"…), so nothing pointed to a club article. The clubs were linked in the article itself, each to the English Wikipedia article of the club's Wikidata QID. After that edit the reader found 20 teams and 380 scores, and every team resolved to a seeded QID. The season names its article like every other one.

**Alternative rejected:** matching the grid's plain names to our team names. It breaks the rule that reference teams are identified only by QID (match-verification spec). Several of those names, such as "Milan", "Roma", "Genoa" and "Torino", are also cities, so a lookup by title would pick the wrong item.

### D3. Teams

Missing spellings are drafted with `tools/propose_teams.py` and then reviewed by hand:

- **One team per Wikidata QID.** A new spelling of a seeded club, such as "Arsenal" next to "Arsenal FC", becomes another alias of that club. It is never a new team.
- **Re-founded or renamed clubs follow Wikidata.** If Wikidata has one item for the club across a refoundation (Parma, Palermo, SPAL and others), we have one team. If it has two items, we have two teams.
- **A spelling maps to exactly one club across all leagues.** If two clubs share a spelling, sync already fails on the ambiguity. That's left to fail, and a review fixes the alias.

### D4. Verification volume

A verified run makes two requests per season with an article: one for the grid, and at least one batch for the QIDs. For all five leagues that's about 170 requests in sequence, each with the existing 20 s timeout and one retry. A one-off probe of all 71 articles with a 0.5 s pause between requests met no rate limiting. The current code has no pause between seasons. **Decision:** no pacing change unless the integration run hits 429s. If it does, a short fixed pause between seasons goes into the verifier, which is a small code change covered by the existing tests.

**Outcome:** the integration run verified the four leagues' 70 seasons with 140 requests in 1 min 53 s, with no 429s, so no pacing was added.

### D6. "Regular Season - N" round labels

openfootball's 2025-26 text files for all five leagues now head rounds with `Regular Season - N` instead of `Matchday N`. Until now this went unnoticed because La Liga, the Premier League, the Bundesliga and Serie A read 2025-26 from the JSON mirror, which is current. Ligue 1's mirror isn't, so its text file failed with "unrecognised round label". The stage rules now map `Regular Season` to `LEAGUE`, and the trailing `- N` to the matchday number.

### D5. Mismatch review

As for La Liga, every `MISMATCH` found by the integration run is reviewed before the PR is opened. Each one ends up as one of:

- **A parser bug.** It gets fixed, with a test.
- **An openfootball error.** It's reported upstream, and the stored score stays as the source has it.
- **A Wikipedia error.** It's recorded in the PR and left to be fixed in the article.

Stored data is never patched by hand.

## Source coverage

**Kickoff time zones.** Each league's oldest and newest files write kickoffs as local wall-clock times: no `UTC±N` offsets appear on the lines, and the times are the league's usual slots.

| League         | Usual slots in the files          | `tz`            |
| -------------- | --------------------------------- | --------------- |
| Premier League | 12:30, 15:00, 17:30, 19:45, 20:00 | `Europe/London` |
| Bundesliga     | 15:30, 18:30, 20:30               | `Europe/Berlin` |
| Serie A        | 18:00, 18:30, 20:45               | `Europe/Rome`   |
| Ligue 1        | 15:00, 17:00, 17:15, 20:45, 21:00 | `Europe/Paris`  |

**Integration run** (empty database, `just sync` then a verified sync of the four leagues):

- Premier League: 27 seasons, 10,260 matches.
- Bundesliga: 17 seasons, 5,202 matches.
- Serie A: 14 seasons, 5,320 matches.
- Ligue 1: 13 seasons, 4,644 matches. 2019-20 has 101 `CANCELLED` fixtures, and the season is `COMPLETED`.
- Verification: every season clean apart from the following.
  - 4 `MISMATCH`, all in Ligue 1. French Wikipedia was used as a third source to settle them:
    - **English Wikipedia errors:** Angers v Saint-Étienne 2016-17 (1–2, en 1–3), Reims v Lens 2024-25 (0–2, en 0–3) and Brest v Lens 2025-26 (3–3, en 3–0, the half-time score). openfootball and French Wikipedia agree in all three.
    - **Bastia v Lyon 2016-17:** abandoned at half-time at 0–0 and awarded 3–0 to Lyon. openfootball has `0-0 [awarded]`, while its other awarded games carry the awarded score (e.g. Sassuolo v Pescara 2016-17, 0-3). This is an openfootball inconsistency, to report upstream. The stored score stays as the source has it.
  - After the three English Wikipedia errors were corrected in the articles and Serie A 2018-19's clubs were linked, a rerun of Serie A and Ligue 1 left only Bastia v Lyon as `MISMATCH`. Serie A 2018-19 verified all 380 matches.
  - 22 `SOURCE_BEHIND`, all in 2026-27: openfootball lagging behind the season in progress.

## Risks / Trade-offs

- **[Risk] Older seasons use different kickoff time conventions** (for example, no times at all). → The parser already handles dateless and timeless lines. The integration run checks every season's match count, and each season's `tz` is checked against a few known kickoffs.
- **[Risk] Ambiguous historical spellings** (for example, "Inter" or "Milan" appearing in other competitions' files). → Sync fails loudly on an unknown or ambiguous name, and `propose_teams.py` flags uncertain QIDs with `# REVIEW`.
- **[Risk] A bigger nightly run** (about 25,000 more matches and 170 Wikipedia requests) if the scheduled run is widened to these leagues. → Measured in the integration run and recorded in the PR. Whether and when the schedule is widened is decided outside this repo.

## Migration Plan

- **Schema:** no change. Deploying the new image changes nothing until a sync runs.
- **Data:** the first sync of the four leagues adds the seasons. 2024-25 is reconciled in place, since matches are keyed by season, stage and teams.
- **Rollback:** revert the seeds. Seasons that were already ingested stay until they're deleted by hand. Sync never deletes seasons.
