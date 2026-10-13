# Design

## Context

The ingestion pipeline (seeds, then the text parser, then the reconciling sync) already handles knockout rounds for the UEFA and FIFA competitions. Before writing this change, every domestic cup file openfootball has was surveyed:

- **Parsing:** all 33 files parse.
- **Round headers:** four styles have no stage rule yet: `Round N`, `N. Round`, `N. Runde` (a German label left in the French file) and `Preliminary round`. The named rounds (`Round of 16`, `Quarterfinals`, `Semi-finals`, `Final`) already map.
- **Match identity:** matches are keyed by (season, stage, home, away). That key collides exactly once, in FA Cup 2023-24 Round 1, where Scarborough Athletic v Forest Green Rovers appears twice with the same home team. The first game ended 1–1, the replay was voided, and the replay of the replay was played at Scarborough. openfootball lists only the two valid games. No other seeded file, league or cup, repeats a pairing within a stage.
- **Teams:** about 730 spellings are not seeded: FA Cup 147, EFL Cup 57, Copa del Rey 255, DFB-Pokal 106, Coppa Italia 52 and Coupe de France 170. Most are lower-division or amateur clubs.
- **DFB-Pokal 2025-26:** the main file is incomplete (proposal.md), and the `openliga/` conversions miss matches in every season.

## Goals / Non-Goals

**Goals:**

- Ingest the six cups with correct stages and no lost games.
- Model the kind of competition (`format`) so super cups and other league cups fit later without another schema change.

**Non-Goals:**

- Wikipedia verification of cups. That needs a match-box reader, which is a follow-up change.
- Qualifying rounds that openfootball doesn't have, such as the FA Cup's qualifying rounds or Coupe de France rounds 1 to 6.
- Partial seasons: DFB-Pokal 2025-26 stays out.

## Decisions

### D1. `format` as a third orthogonal competition field

Competitions get a `format` column, `competition_format` enum: `LEAGUE`, `CUP`, `LEAGUE_CUP`, `SUPER_CUP`, `TOURNAMENT`. It is set in every seed entry, written on sync, and exposed in `CompetitionOut` with a `?format=` filter. `TOURNAMENT` covers the existing group-or-league-phase-plus-knockout competitions.

**Alternatives:**

- **Deriving the format from the stages present.** Rejected. A cup season with only named rounds would look the same as a tournament's knockout phase.
- **A free-text `type`.** Rejected, because it can't be filtered or validated.

**Migration:** the column is added with a temporary default of `LEAGUE`. The migration then sets `TOURNAMENT` on the eight existing tournaments, found through their Wikidata QIDs in `external_ref`, so the API is right before the next sync, and drops the default. From then on the sync sets the value from the seeds.

### D2. Stages `ROUND` and `PRELIMINARY`

- **`ROUND`:** the numbered rounds become stage `ROUND`, with the number in the existing `matchday` column. The column is not renamed, to keep the API additive; its OpenAPI description says "matchday, or round number for `ROUND`".
- **`PRELIMINARY`:** the Copa del Rey and Coppa Italia preliminary rounds are part of the competition proper, so they're `PRELIMINARY`, not `QUALIFYING`.
- **Rules:** `(?:round|runde)\s*(\d+)` and `(\d+)\.\s*(?:round|runde)` match `ROUND`, after the existing named-round rules so that `Round of 16` keeps `R16`. `prelim` matches `PRELIMINARY`.

**Alternative:** mapping numbered rounds to R128, R64 and so on by counting teams. Rejected. Round sizes vary (byes, uneven entries), and the source's own numbering is what the competitions use.

**Migration:** `ALTER TYPE stage ADD VALUE` for both values. PostgreSQL can't remove enum values, so the downgrade recreates the type.

### D3. `occurrence` in the match identity

`match.occurrence` is a SMALLINT, `NOT NULL DEFAULT 1`. The unique key becomes (season, stage, home, away, occurrence).

During a season's sync, the parser's matches are walked in source order, keeping a counter per (stage, home, away). A repeated listing gets the next occurrence only if the previous listing of that pairing has a score. Otherwise it's the same game rescheduled, and the existing postponement handling applies (`original_kickoff_utc`).

**Alternatives:**

- **Keying by kickoff.** Rejected. It breaks the postponement rule, under which a moved game keeps its UUID.
- **Dropping the earlier game.** Rejected, because it loses a real result.

**Risk:** if the source later inserts an earlier occurrence of a pairing that already has two games, the occurrences shift and the UUIDs swap. This is accepted: it has happened once in about 50,000 matches, and the sync stays correct, only the identities move.

### D4. Teams

As before:

1. Draft with `tools/propose_teams.py`.
1. Review every `# REVIEW`.
1. Rule: one team per Wikidata QID. A reserve or B team, if one appears, is a separate club with its own QID.
1. An amateur club with no unambiguous Wikidata item is still seeded, with `wikidata` left out. The schema allows that, and it's the only way to keep its matches. Each such club is listed in the PR.

Countries come from the cup's country, except for clubs that play in another country's pyramid. For example, Welsh clubs in English cups get `GB-WLS`, and AS Monaco gets `MC`.

### D5. Seeds

| Cup             | `file`                            | `tz`            | `format`     |
| --------------- | --------------------------------- | --------------- | ------------ |
| FA Cup          | `england/<label>/facup.txt`       | `Europe/London` | `CUP`        |
| EFL Cup         | `england/<label>/eflcup.txt`      | `Europe/London` | `LEAGUE_CUP` |
| Copa del Rey    | `espana/<label>/cup.txt`          | `Europe/Madrid` | `CUP`        |
| DFB-Pokal       | `deutschland/<label>/cup.txt`     | `Europe/Berlin` | `CUP`        |
| Coppa Italia    | `italy/<label>/cup.txt`           | `Europe/Rome`   | `CUP`        |
| Coupe de France | `europe/france/2024-25_frcup.txt` | `Europe/Paris`  | `CUP`        |

- No `json` (football.json has no cups) and no `wikipedia` (no cup verification yet).
- Each `tz` is checked against a few known kickoffs, as for the leagues.

## Source coverage

**Kickoff time zones.** The cup files write local wall-clock times with no `UTC±N` offsets, and the times are the usual slots in each country:

| Cup             | Most common times in the files | `tz`            |
| --------------- | ------------------------------ | --------------- |
| FA Cup, EFL Cup | 19:45, 20:00, 15:00, 12:30     | `Europe/London` |
| Copa del Rey    | 21:00, 19:00, 21:30            | `Europe/Madrid` |
| DFB-Pokal       | 20:45, 18:30, 18:00, 15:30     | `Europe/Berlin` |
| Coppa Italia    | 21:00, 18:30, 20:45            | `Europe/Rome`   |
| Coupe de France | 21:00, 19:00, 17:00            | `Europe/Paris`  |

**Rounds.** Every round header in the 32 cup seasons maps to a stage.

**Unscored matches.**

- EFL Cup 2019-20 Sheffield Wednesday v Bury and 2021-22 Harrogate Town v Rochdale are `[cancelled]` in the source.
- EFL Cup 2020-21 Leyton Orient v Tottenham Hotspur (called off and awarded to Tottenham) has neither a score nor a tag, so that season stays `IN_PROGRESS`. This is a source gap. It is not patched.

**Teams.** 723 cup spellings were missing:

- 8 became aliases of seeded clubs. The draft also matched "AC Paris 15" to Paris Saint-Germain, which was rejected.
- 712 new clubs were added. 648 have a Wikidata QID: each one was checked to be a football club (instance of) in the cup's country, and labels that barely overlapped the spelling were reviewed by hand. The other 64, amateur clubs with no unambiguous item, have no QID.
- Two countries differ from the cup's: Welsh clubs in English cups are `GB-WLS`, and FC Andorra is `AD`.

**Integration run** (empty database, two syncs):

- Both runs exit 0, with 35,183 matches, and the second run leaves the match table byte-identical.
- Cups: FA Cup 981, EFL Cup 649, Copa del Rey 631, DFB-Pokal 441, Coppa Italia 259 and Coupe de France 200, matching the files.
- The leagues are unchanged.

## Risks / Trade-offs

- **[Risk] Amateur clubs with no or ambiguous Wikidata items.** → They're seeded without a QID (D4) and listed in the PR. Future verification simply won't match them.
- **[Risk] Super cups and other league cups have no source.** → `format` already has `SUPER_CUP` and `LEAGUE_CUP`, so adding them later is seed data only.
- **[Trade-off] `matchday` holds round numbers for cups.** → It's documented in OpenAPI and avoids a breaking rename.
- **[Risk] Clients switching over `stage` see new values.** → This is called out as breaking in the proposal and the README.

## Migration Plan

- **Upgrade:** one Alembic revision. It adds the `competition_format` type and column (with a temporary default), adds the two `stage` values, and adds `match.occurrence` with default 1. It also swaps the unique constraint. Existing rows all get `occurrence` 1, so the new constraint can't be violated.
- **Deploy:** the API runs `alembic upgrade head` on start. The next sync writes `format` and ingests the cups.
- **Rollback:** the downgrade drops `occurrence`. This would fail if any match has `occurrence` > 1, so the downgrade first deletes those rows, of which there is one today. It also drops `format`, and recreates `stage` without the new values, failing if any rows use them; the downgrade documents deleting cup seasons first.
