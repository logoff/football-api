# Add Match Events — Design

## Context

Matches, goals and squads are synced per season by `sync_season` from the season's `file:` (or its JSON mirror when current), then verified against Wikipedia. Child rows keep a UUID plus a `(match_id, [side,] ordinal)` key; coverage is reported per season (`scorers_coverage`, `players_coverage`), computed from what the source contains. See `proposal.md` for motivation; behaviour is specified in `specs/`.

Event data lives in openfootball's `-full` files. Surveyed on 2026-10-19 over the checkouts in `.cache/sources`:

| Source                              | Lineups                                 | Subs | Cards                                     | Referee            | Attendance                | Card notation |
| ----------------------------------- | --------------------------------------- | ---- | ----------------------------------------- | ------------------ | ------------------------- | ------------- |
| World Cup 1930–2026                 | all                                     | all  | all (few before 1970, when cards came in) | all                | 2018 on                   | inline        |
| Club World Cup 2000–2017, 2020–2025 | all                                     | all  | all                                       | all but 2015, 2016 | 2018 on                   | inline        |
| Club World Cup 2018, 2019           | starters only, 2018 with no line groups | none | none                                      | all                | all                       | —             |
| 2025-26 leagues (5)                 | all                                     | all  | all                                       | all                | all but 2 Ligue 1 matches | card lines    |

Inline tags seen: `[Y m']`, `[R m']`, `[Y/R m']` (3,595 / 164 / 16), and each `[Y/R]` follows a `[Y]` on the same player. Card lines seen: `Yellow:`, `Yellow-Red:`, `Red:`; a `Yellow-Red:` player is also listed under `Yellow:`. The Premier League's 14 `Yellow-Red:` entries match the 14 `Y/R` bookings in `football.json/2025-26/en.1-full.json`.

For every World Cup and 2025-26 league season, parsing the `-full` file with today's parser gives the same matches, kickoffs, scores and goals as the synced file. The only differences are venue names (and, for the leagues, an inline UTC offset), which this change doesn't use.

Source shapes:

```
Sun Jul 13 15:00 UTC-4 @ Giants Stadium, New York/New Jersey (East Rutherford), Att: 81118
  Chelsea FC (ENG) v Paris Saint-Germain (FRA)  3-0
     (Cole PALMER 22', 30', JOAO PEDRO 43')

Chelsea FC: Robert SANCHEZ - Marc CUCURELLA, Levi COLWILL [Y 81'], Trevoh CHALOBAH,
      Reece JAMES [c] (77' Kiernan DEWSBURY-HALL), Malo GUSTO [Y 40'] - Enzo FERNANDEZ (61' ANDREY SANTOS),
      ...
Refs: Alireza FAGHANI (AUS)
```

```
Sun Sep 14 14:00 UTC+1 @ Turf Moor, Burnley, Att: 21678
  Burnley v Liverpool  0-1 (0-0)
     (MOHAMED SALAH 90+5'(p))

Burnley: Martin DUBRAVKA - Maxime ESTEVE, Hjalmar EKDAL, Josh Laurent, Lesley UGOCHUKWU,
      ...
    Yellow: Lesley UGOCHUKWU 16'
    Yellow-Red: Lesley UGOCHUKWU 84'

Liverpool: ALISSON - Virgil VAN DIJK [c], Ibrahima KONATE (87' Jeremie FRIMPONG),
      ...
    Yellow: Milos KERKEZ 22', Conor Bradley 75'

Refs: Michael Oliver, Stuart Burt, James Mainwaring
```

## Goals / Non-Goals

**Goals:**

- One lineup-block parser for both card notations, run in a single pass.
- Leave every synced match, goal and verification status as it is: events attach to matches that already exist.
- Coverage reported honestly per part and per season.
- The same identity and idempotency model as goals, so sync stays byte-for-byte stable.

**Non-Goals:**

- A general event timeline table (`match_event` with a `type` column). Three narrow tables are simpler to query and type-check; a timeline can be a view later.
- Switching the synced `file:` to the `-full` file, taking venues or offsets from it, or reading the JSON `-full` mirrors.
- Unused substitutes (only the JSON mirrors list the bench, and only for England and Germany).
- Referee as an entity, referee country, assistant referees.
- Inferring tactical positions beyond the source's line grouping.

## Decisions

### D1. Events come from their own seed field

```yaml
- label: 2025-26
  start_year: 2025
  file: england/2025-26/1-premierleague.txt
  json: football.json/2025-26/en.1.json
  events: england/2025-26/1-premierleague-full.txt
```

`sync_season` reads matches as today, then, if `events:` is set, parses that file a second time for event blocks only. For the Club World Cup, `events:` names the same file as `file:`.

- **Why not point `file:` at the `-full` file?** For the leagues, sync uses the JSON mirror whenever it's current, so the text file isn't what's read. Swapping `file:` would also pull in venue names and offsets, which would create rows and change kickoffs: a change of its own, with its own verification.
- **Why not the JSON `-full` mirrors?** Only England, Germany and Austria have them. The text path covers every season in scope with one parser.

### D2. Linking an events-file match to its synced match

The events file is parsed with the existing `parse_text` (for date, teams and line numbers) plus the new lineup-block reader. Each parsed match is linked by `(day, home team, away team)`, with the team spellings resolved through the same `resolve_team` used for matches, to the match synced from `file:` in that season. A match in the events file that links to no synced match, or to more than one, fails the season's sync with the events file's path and line number, the same as an unknown team does today. The survey showed the keys are identical for every season in scope, so a failure means a real divergence between the two files.

A match with no lineup block keeps no events, and its coverage follows the season's. One case today: Club World Cup 2020's Al Duhail v Auckland City, 3-0 after Auckland withdrew. A synced match with no counterpart in the events file (none today) is handled the same way.

### D3. Three tables, ordinal-keyed

```
lineup_entry   id uuid PK, match_id, side, ordinal, player_id NULL, player_name,
               role (STARTER|SUBSTITUTE), line_index NULL, is_captain
               UNIQUE (match_id, side, ordinal)
substitution   id uuid PK, match_id, side, ordinal, minute, added_minute NULL,
               player_off_id NULL, player_off_name, player_on_id NULL, player_on_name
               UNIQUE (match_id, side, ordinal)
card           id uuid PK, match_id, side, ordinal, minute, added_minute NULL,
               player_id NULL, player_name, kind (YELLOW|SECOND_YELLOW|RED)
               UNIQUE (match_id, side, ordinal)
match          + referee_name NULL, + attendance NULL
season         + lineups_coverage, + substitutions_coverage, + cards_coverage
```

- **UUID PK + `(match_id, side, ordinal)` unique key**, mirroring goals: UUIDs are kept for future references; the ordinal gives an idempotent upsert. Ordinals beyond the source's count are deleted.
- **Ordinal is source order within the side.** Lineup entries: the starters in listing order, then the substitutes who came on in the order their brackets open. Substitutions: the order their brackets open. Cards: inline tags in listing order; with card lines, `Yellow:`, then `Yellow-Red:`, then `Red:`, each in listing order. The API sorts substitutions and cards by `(minute, added_minute, ordinal)`, so the card-line grouping isn't visible to clients.
- **Keyed on `(match_id, side, ordinal)`, not on the player:** the player reference is nullable, and one player can get several cards.
- **`player_name` is always stored**, title-cased by the same rule as goal scorers, even when `player_id` resolves. Responses don't need a join to show a name, and an unresolved name isn't lost.
- **Formation is derived, not stored**: worked out from `line_index` counts at read time, so there's one source of truth. It's null when a side's starters form a single group (Club World Cup 2018).
- **Child rows cascade on match delete.** A match the source no longer lists already takes its goals with it; events go the same way.
- Alternative considered: delete and reinsert per match. Rejected for the same reason as for goals: UUIDs would change on every sync.

### D4. Parsing the lineup block

1. A lineup starts at an unindented `<Team>: ` line after a match and its goal block, and continues over indented lines that aren't card lines. Blank lines between the two sides' lineups don't end the block. The home lineup comes first, then the away one. Each name before the colon must equal that side's spelling on the match line with any trailing country code removed (`Chelsea FC:` under `Chelsea FC (ENG) v …`); this holds for every match in scope. A `Penalties:` shootout block between the goals and the lineups is skipped, as the match parser already does.
1. Indented `Yellow:`, `Yellow-Red:` and `Red:` lines after a lineup belong to that side. Each is a comma-separated list of `<name> <minute>`.
1. `Refs:` / `Ref:` ends the match's block. Its first name, without a bracketed country, is the referee. `Att: <n>` on the match's date or venue line is the attendance.
1. Split line groups on `" - "` (space, dash, space). Hyphenated surnames (`DEWSBURY-HALL`, `ZAIRE-EMERY`) have no spaces around the dash and stay whole.
1. Within a group, split players on top-level commas (commas inside brackets belong to substitution chains).
1. Each player token gives a name, an optional `[c]`, zero or more card tags, and an optional bracketed substitution `(<min>' <token>)`, parsed recursively.
1. A card tag belongs to the token it follows, so a card inside a substitution bracket belongs to the substitute.
1. Card kinds: `Y` and `Yellow:` → `YELLOW`; `Y/R` and `Yellow-Red:` → `SECOND_YELLOW`; `R` and `Red:` → `RED`. Sources list the first yellow separately in both notations, so a sending-off for two yellows is stored as two cards.
1. Minutes parse as `<minute>(+<added>)?'`, with the goal parser's minute rule. Sources sometimes write added time as a plain minute (`94'`), which is stored as written.
1. Anything else in the block (notes, unknown tags) fails sync with file and line. A lineup we only half understand isn't stored.

### D5. Coverage from the data, per part, per season

`season.lineups_coverage` is `full` when the season's events file gives lineups for its matches, and `none` otherwise or with no `events:`. `substitutions_coverage` and `cards_coverage` work the same way for brackets and card tags or lines. This is the rule `scorers_coverage` already uses (`full` if any match lists goals). A match with no cards in a `cards: full` season had no cards.

The match response repeats its season's values under `coverage`, next to `scorers`. Referee and attendance are plain nullable fields with no coverage flag: null means the source doesn't say.

`substitutions` gets its own flag because Club World Cup 2018 and 2019 have starters but no substitutions. Without it, `lineups: full` would suggest no one was substituted.

### D6. Player resolution

Names resolve against the team-season's squad with the case- and accent-insensitive matcher that goals use. Squads are ingested only for World Cup 2022 and Club World Cup 2025, so elsewhere every event row keeps a null `player_id` and its name. Adding the other editions' squad files is a seeds-only follow-up.

## Risks / Trade-offs

- [Source line grouping isn't a true formation: the Chelsea final reads as 5-3-2] → The spec says formation reflects source grouping, and so does the API description.
- [Strict parsing means one malformed lineup fails the season] → Same policy as unknown teams; golden tests over every events file in scope catch it before release, and the error names file and line.
- [The events file and the synced file drift apart (a fix lands in one first)] → D2 fails the season instead of guessing; the plain file stays the source of truth for matches.
- [League lineups without player links are less useful] → Names are still there, and the gap is reported (`players: none`). Linking league players needs squad data openfootball doesn't publish.

## Migration Plan

One additive Alembic migration: three tables, two nullable `match` columns, three `season` columns with server default `none`. Downgrade drops them. The first sync after deploy fills events and coverage. No existing row changes apart from the new columns.
