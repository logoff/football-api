# Tasks

## 1. Parser

- [x] 1.1 Record a baseline: parse every currently seeded file and save its match list. Verify that the script runs.
- [x] 1.2 Accept `<Month> <day>` dates with an optional weekday and year, alone or prefixing a match line with an optional time and venue (D1). Verify with parser tests for each of the five layouts, using excerpts as fixtures.
- [x] 1.3 Add the stage rules for `Gruppe`, ordinal rounds and fifth place (D3), and add `FIFTH_PLACE` with its Alembic revision. Verify with `normalize_stage` cases, an upgrade/downgrade/upgrade run, and `alembic check`.
- [x] 1.4 Re-parse every currently seeded file. Verify that the match lists are identical to the baseline.

## 2. Seeds

- [x] 2.1 List every edition of the eight competitions in `seeds/competitions.yaml` with its file and `tz` (D4), leaving out undated editions (D2). Verify with a script that each listed file parses and every round label maps.
- [x] 2.2 Check each `tz` against known kickoffs (two per competition, plus every Euro and Copa América edition's header). Record the results in design.md under "Source coverage".
- [x] 2.3 Draft and review the missing team spellings (D5). Verify that the seed loader accepts them, that there are no QID-shaped names and no label mismatches, and that `just sync` raises no unknown-team error.

## 3. Docs

- [x] 3.1 Update the README coverage table (editions per competition, the new `FIFTH_PLACE` stage, and the excluded editions) and the `openspec/config.yaml` scope context. Verify that mdformat leaves no changes.

## 4. Integration

- [x] 4.1 Run a full sync on an empty database, twice. Verify the per-edition match counts against the files, that the second run is identical, and that existing competitions' counts are unchanged.
- [x] 4.2 Verify that `just typecheck`, `just test` and `openspec validate extend-international-history --strict` all pass.

## Workflow follow-up

- Follow-up change: verify the international competitions against Wikipedia (multi-article seasons).
- Keeping Champions League 2025-26 and Libertadores 2026 current needs the scheduled run to include them, which is an infra decision outside this repo.
- Archive this change once it's merged.
