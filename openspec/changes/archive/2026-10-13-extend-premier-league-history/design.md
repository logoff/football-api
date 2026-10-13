# Design

## Context

The per-season seed shape, the Wikipedia grid verifier and the date-only kickoff handling all exist already (see the archived changes `verify-and-schedule-la-liga` and `extend-and-verify-top-leagues`). Investigating the eight archive files found:

- **Parsing:** every file parses with the current parser.
- **Rounds:** every round maps to `LEAGUE`.
- **Matches:** every match has a score.
- **Kickoff times:** only 1998-99 has times. The other seasons give dates only.
- **Wikipedia:** each season's article has a grid with as many scores as the file has matches (462 or 380).

## Goals / Non-Goals

**Goals:** ingest and verify the 1992-93 to 1999-00 Premier League seasons with seed data only.

**Non-Goals:** the archive's pre-Premier League First Division seasons (`1880s`, `1890s` and 1999-00's lower divisions). They're a different competition and out of scope.

## Decisions

### D1. Seeds point into the archive folder

`file: england/archive/1990s/<label>/1-premierleague.txt` and `tz: Europe/London`, with no `json` because football.json starts at 2010-11.

- **`wikipedia`:** `YYYY–YY FA Premier League`, except `1999–2000 FA Premier League`, the article's actual title.
- **Labels:** labels stay in our `YYYY-YY` form (`1999-00`), matching the folder name.

### D2. Wimbledon F.C. is its own team

The old Wimbledon F.C. (Q19482) is not AFC Wimbledon (Q48851, founded 2002) and not Milton Keynes Dons (Q248188). Wikidata keeps three items, and teams follow Wikidata (one team per QID). The new entry is named "Wimbledon".

### D3. Date-only kickoffs

A kickoff without a time is stored at midnight UTC on the match date. That comes from the fix "Keep the date of date-only kickoffs" (#8); before it, files with a named zone stored local midnight, which during British Summer Time falls on the previous UTC day. Seven of the eight seasons have no times in the source, so their `kickoff_utc` values are dates. This is the source's precision, not a parser loss.

## Source coverage

**Integration run** (empty database, `just sync-competition Q9448 --verify`, 1 min 22 s):

- 35 seasons and 13,546 matches.
- 1992-93 to 1994-95: 462 matches each, all `VERIFIED`.
- 1995-96 to 1999-00: 380 matches each, all `VERIFIED`.
- No `MISMATCH`. The only statuses other than `VERIFIED` are 10 `SOURCE_BEHIND` matches in 2026-27, the season in progress.

## Risks / Trade-offs

- **[Trade-off] Date-only kickoffs for 1992-93 to 1997-98 and 1999-00.** → It's documented in the README coverage notes.
- **[Risk] Archive files may later move upstream.** → Sync fails loudly on a missing file. The seed then needs a path update.
