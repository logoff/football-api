# Add Match Events — Tasks

## 1. Schema

- [ ] 1.1 Add SQLAlchemy models `LineupEntry`, `Substitution`, `Card` (cascading on match delete), `match.referee_name` / `match.attendance`, and `season.lineups_coverage` / `substitutions_coverage` / `cards_coverage` per `design.md` D3; verify `just typecheck` passes.
- [ ] 1.2 Generate the Alembic migration with `UNIQUE (match_id, side, ordinal)` on each new table and server default `none` on the coverage columns; verify upgrade and downgrade both run cleanly against a database synced from `main`.

## 2. Parser

- [ ] 2.1 Lineup-block reader (D4): finds each match's block, checks the home-then-away team headers against the match line's spellings without country codes, skips `Penalties:` blocks, collects card lines per side, reads `Refs:` and `Att:`; verify golden fixtures of the Club World Cup 2025 final (inline) and Burnley v Liverpool 2025-26 (card lines, blank line between sides).
- [ ] 2.2 Token parser: line groups on `" - "`, top-level comma split, `[c]`, card tags (`Y`, `Y/R`, `R`), recursive `(<min>' <token>)` substitutions; verify unit tests for hyphenated names, the chained `EMAM ASHOUR (14' ZIZO (79' MOHAMED AFSHA))` case, a card inside a substitution bracket, `[c] [R 90+2']` on one player, and an unknown tag failing with file and line.
- [ ] 2.3 Card-line parser for `Yellow:`, `Yellow-Red:`, `Red:` (`<name> <minute>` lists, added time); verify unit tests including a name with a hyphen and `90+11'`.
- [ ] 2.4 Run the parser over every events file in scope (23 World Cup, 21 Club World Cup, five 2025-26 leagues); verify per file that card totals equal the source's tag or line-entry counts, every match with a lineup has two sides of 11 starters, captains match `[c]` counts, and Club World Cup 2020 Al Duhail v Auckland City yields no events.

## 3. Ingestion

- [ ] 3.1 Add `events:` to `SeasonSource` and to the 49 seasons in `seeds/competitions.yaml` (for the Club World Cup, the same path as `file:`); verify the seed loader test and that `repos_for` needs no new repository.
- [ ] 3.2 In `sync_season`, parse the events file and link its matches to synced matches by `(day, home team, away team)` (D2), failing on no link or more than one; verify a test for each failure and one where the season reads its JSON mirror.
- [ ] 3.3 Resolve event player names against the team-season squad with the goals' matcher and title-casing (D6); verify a World Cup 2022 test that resolves and a Premier League 2025-26 test that keeps names with null `player_id`.
- [ ] 3.4 Upsert lineup entries, substitutions and cards by `(match_id, side, ordinal)`, delete surplus ordinals, set `referee_name` and `attendance`, and set the three season coverage values from the parsed data (D5); verify the idempotency test (sync twice, identical rows and UUIDs), the "source drops a card" test, and that a removed match takes its events.
- [ ] 3.5 Verify that, after a full `just sync`, every match, goal and verification status from before this change is unchanged (same UUIDs and values), and that coverage is `full`/`full`/`full` for World Cup 2022, `full`/`none`/`none` for Club World Cup 2019 and `none` for a Champions League season.

## 4. API

- [ ] 4.1 Add `referee`, `attendance` to the match schema and `lineups`, `substitutions`, `cards` to the match and season coverage schemas; verify OpenAPI shows them and API tests assert them.
- [ ] 4.2 Support `expand=lineups,substitutions,cards` on `/v1/matches/{id}` and `/v1/matches`, with per-side `formation` (null for one group) and substitutions and cards ordered by `(minute, added_minute, ordinal)`; verify API tests for the Club World Cup 2025 final (Chelsea's formation from the source grouping, PSG red card at 85'), a Club World Cup 2018 match (null formation), and a non-expanded response without the keys.
- [ ] 4.3 Document event coverage per competition and season, and the "formation reflects source grouping" caveat, in OpenAPI descriptions, the README's coverage table and `openspec/config.yaml`'s context; verify they render in `/docs` and `mdformat` leaves the README unchanged.

## 5. Integration

- [ ] 5.1 On a clean database, `just up && just sync`, then `curl` a World Cup 2022 match and a 2025-26 Serie A match with `?expand=lineups,substitutions,cards`; verify lineups, substitutions and cards are present, then that `just test` and `just typecheck` pass.
