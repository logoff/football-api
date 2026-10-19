# Add Match Events

## Why

The API stops at final scores and goal scorers. Lineups, substitutions and cards are the next layer clients expect from a football API. openfootball already publishes them, in `-full` files that sit next to the files we sync, for about 3,000 matches we already hold:

| Competition                                           | Seasons            | Matches | Source                                                                      |
| ----------------------------------------------------- | ------------------ | ------- | --------------------------------------------------------------------------- |
| FIFA World Cup                                        | 1930–2026 (all 23) | 1,068   | `worldcup/more/<year>_full.txt`                                             |
| FIFA Club World Cup                                   | 2000–2025 (all 21) | 224     | `club-worldcup/more/<year>_clubworldcup-full.txt` (already the synced file) |
| Premier League, La Liga, Bundesliga, Serie A, Ligue 1 | 2025-26            | 1,752   | `<country>/2025-26/*-full.txt`                                              |

Checked on 2026-10-19: for every World Cup and 2025-26 league season, the `-full` file lists the same matches, scores and goals as the file we sync now, so we can take events from it without changing any match or its Wikipedia verification. No other in-scope competition or season has event data.

## What Changes

- **Events from a separate source file per season.** A new optional `events:` field on a season in `seeds/competitions.yaml` names its `-full` file. Matches, scores and goals still come from `file:` (or its JSON mirror), so nothing that's synced and verified today changes.
- **One parser for two text notations:**
  - *inline* (World Cup, Club World Cup): cards as tags on the player, `Reece JAMES [Y 81']`, `[R 85']`, `[Y 20'] [Y/R 78']`;
  - *card lines* (2025-26 leagues): cards listed after each lineup, `Yellow: Milos KERKEZ 43', …`, `Yellow-Red: …`, `Red: …`.
    Both share the lineup notation: line groups separated by `-`, `[c]` for the captain, substitutions in brackets, chained ones nested (`EMAM ASHOUR (14' ZIZO (79' MOHAMED AFSHA))`).
- **Stored per match:** lineups (starters and the substitutes who came on, captain, source line group), substitutions, cards (`YELLOW`, `SECOND_YELLOW`, `RED`), the referee's name and the attendance.
- **API:** `GET /v1/matches` and `/v1/matches/{id}` accept `expand=lineups,substitutions,cards`; `referee` and `attendance` are always present (nullable). Lineups carry a per-side `formation` derived from the source's line groups.
- **Coverage per part, per season**, like `scorers` today: `coverage.lineups`, `coverage.substitutions` and `coverage.cards` on matches and seasons, each `full` or `none`, worked out from what the season's events file contains. Club World Cup 2018 and 2019, for example, list starting line-ups but no substitutions or cards.
- Player names link to a squad player where the season has squads (World Cup 2022, Club World Cup 2025). Everywhere else they're stored as names, as goal scorers are today.

## Capabilities

### New Capabilities

- `match-events`: lineups, substitutions, cards, referee and attendance: how they're parsed from both notations, linked to matches and players, exposed, and how per-season coverage is reported.

### Modified Capabilities

- `matches`: the match record gains `referee` and `attendance`, its `coverage` gains `lineups`, `substitutions` and `cards`, and `expand` gains the three event values.
- `ingestion`: seasons can name an events file; the idempotency rules gain natural keys for lineup entries, substitutions and cards; matches removed from the source take their events with them.

## Impact

- **Schema:** new tables `lineup_entry`, `substitution`, `card`; new nullable columns `match.referee_name`, `match.attendance`; new season columns `lineups_coverage`, `substitutions_coverage`, `cards_coverage`. One additive Alembic migration.
- **Seeds:** `events:` on the 23 World Cup, 21 Club World Cup and five 2025-26 league seasons.
- **Ingestion:** a lineup-block parser, and a step in `sync_season` that links each events-file match to its synced match.
- **API:** new fields and `expand` values; no breaking changes.
- **Out of scope:**
  - Squads for the other World Cup and Club World Cup editions. openfootball has them (`<year>_squads.txt`), so a follow-up change can add them and lineups will start linking to players.
  - Venues and inline UTC offsets from the `-full` files.
  - Unused substitutes (the bench). Only the JSON mirrors list it, and only for England and Germany.
  - Verifying events against Wikipedia.
  - Assistant referees, referees as an entity, xG, shots, pitch positions.
  - The 2026-27 league season: openfootball has no `-full` file for it yet. When one appears, adding `events:` to the seed is enough.
