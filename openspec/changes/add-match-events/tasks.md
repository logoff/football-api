# Add Match Events — Tasks

Prerequisite: `init-football-api-v0.1` implemented (match, player, squad, goal ingestion and `/v1/matches`).

## 1. Schema

- [ ] 1.1 Add SQLAlchemy models `LineupEntry`, `Substitution`, `Card` and `match.referee_name` / `match.attendance` per `design.md`; verify `just typecheck` passes.
- [ ] 1.2 Generate the Alembic migration with `UNIQUE (match_id, side, ordinal)` on each new table; verify upgrade and downgrade both run cleanly against a v0.1 database.

## 2. Parser

- [ ] 2.1 Minute parser for `<m>'` and `<m>+<a>'`; verify unit tests cover `22'`, `90+5'`, `116'`.
- [ ] 2.2 Lineup-block reader that joins continuation lines per team and extracts `Refs:` and header `Att:`; verify on a golden fixture of the Club World Cup final.
- [ ] 2.3 Token parser: line groups on `" - "`, top-level comma split, `[c]`, card tags (`Y`, `R`, `Y/R` → `SECOND_YELLOW`), recursive `(<min>' <token>)` substitutions; verify unit tests for hyphenated names, the chained `EMAM ASHOUR (14' ZIZO (79' MOHAMED AFSHA))` case, and a card inside a substitution bracket.
- [ ] 2.4 Run the parser over all 63 matches of `2025_clubworldcup-full.txt`; verify totals match the source tag counts (228 `Y`, 11 `R`, 5 `Y/R`, 2 captains per match) and every side has 11 starters.

## 3. Ingestion

- [ ] 3.1 Resolve event player names against the team-season squad using v0.1's case- and accent-insensitive matcher and title-casing; verify a test where an unknown name keeps `player_name` with null `player_id`.
- [ ] 3.2 Upsert lineup entries, substitutions and cards by `(match_id, side, ordinal)` and delete surplus ordinals; set `referee_name` and `attendance`; wire into `just sync`; verify the idempotency test (sync twice, byte-equal rows and UUIDs) and the "source drops a card" test.
- [ ] 3.3 Mark the Club World Cup `-full` source as event-bearing in the sync config; verify `coverage.events` is `full` for all 63 matches and `none` for a Premier League match.

## 4. API

- [ ] 4.1 Add `referee`, `attendance`, `coverage.events` to the match schema; verify OpenAPI shows them and API tests assert their presence.
- [ ] 4.2 Support `expand=lineups,substitutions,cards` on `/v1/matches/{id}` and `/v1/matches`, with per-side `formation` derived from line groups; verify API tests for the final (Chelsea `formation` from source grouping, PSG red card at 85') and for a non-expanded response omitting the keys.
- [ ] 4.3 Document event coverage (Club World Cup 2025 only) and the "formation reflects source grouping" caveat in OpenAPI descriptions and the README; verify both render in `/docs`.

## 5. Integration

- [ ] 5.1 On a clean machine, `just up && just sync` then `curl 'localhost:8000/v1/matches/<final-id>?expand=lineups,substitutions,cards'`; verify lineups, 5 substitutions per side max, and cards are present, and `just test` passes.
