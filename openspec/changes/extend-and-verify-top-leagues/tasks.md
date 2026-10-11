# Tasks

## 1. Seeds: seasons

- [x] 1.1 List the Premier League's 27 seasons (2000-01 to 2026-27) in `seeds/competitions.yaml`. Set `file` and `tz`, set `json` from 2010-11, and set `wikipedia` to the actual article title (`FA Premier League` up to 2006-07). Verify with a script, run in the PR, that each file parses to its `# Matches` header count.

- [x] 1.2 Do the same for the Bundesliga (17 seasons, 2010-11 to 2026-27), Serie A (14 seasons, 2013-14 to 2026-27; no `wikipedia` for 2018-19, with a comment saying why) and Ligue 1 (13 seasons, 2014-15 to 2026-27, `_fr1.txt` files). Verify with the same script.

- [x] 1.3 Check each league's `tz` on its oldest and newest season against a few kickoffs whose local time is known. Record the checks in design.md under "Source coverage". Verify that the stored UTC kickoffs match.

- [x] 1.4 Map openfootball's new `Regular Season - N` round labels (2025-26 text files) to `LEAGUE`, matchday N (design D6). Verify with a `normalize_stage` test case and a Ligue 1 2025-26 sync.

## 2. Seeds: teams

- [x] 2.1 Draft the missing spellings with `tools/propose_teams.py`. Review them by D3: new spellings of seeded clubs become aliases, new clubs get a QID and a country, and every `# REVIEW` is resolved. Verify that a full local `just sync` raises no unknown-team or ambiguous-name error.
- [x] 2.2 Verify that the Wikidata check in the sync passes for every new QID, and that no QID appears on two teams (seed loader test).

## 3. Tests

- [x] 3.1 Add a sync test with a fixture season containing `[cancelled]` fixtures. Verify that they are stored as `CANCELLED` with no score, that the season ends `COMPLETED`, and that verification gives them no status.
- [x] 3.2 Add a verification test for a season seeded without `wikipedia` inside a competition whose other seasons have one. Verify that the season is skipped without a warning and the others are verified.
- [x] 3.3 Update the tests and examples that use the Premier League as the competition without verification so they use a cup instead. Verify that `just test` passes.

## 4. Docs

- [x] 4.1 Update the README coverage table (season ranges per league, and which are verified, noting Serie A 2018-19) and the `openspec/config.yaml` scope context. Verify that mdformat leaves no changes.

## 5. Integration

- [x] 5.1 Full local run on an empty database: `just sync`, then `just sync-competition` for the four leagues with `--verify`. Verify the season and match counts per league, and record the run time and number of Wikipedia requests. Review every `MISMATCH` by D5 and record the outcome in the PR. If 429s show up, add the pause from D4 with a test.
- [x] 5.2 Verify that `just typecheck`, `just test` and `openspec validate extend-and-verify-top-leagues --strict` all pass.

## Workflow follow-up

- Open the PR without describing any deployment. Widening the scheduled run to these leagues happens outside this repo, after the new image is published.
- Archive this change once it's merged.
