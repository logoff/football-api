# Tasks

## 1. Reader

- [ ] 1.1 Add `Final phase`, `Tournament phase` and `Qualifying phase` to the wrapper headings (design D2). Verify with `round_label` and `normalize_stage` tests: `Final phase / Third round` is `ROUND` 3, `Tournament phase / Semi-finals` is `SF`, and `Qualifying phase / Preliminary round` is `PRELIMINARY`. Check that the existing Champions League label tests still pass.
- [ ] 1.2 Add `wikipedia_skip` to the season seed, valid only with `wikipedia_source`. Drop the boxes under a listed heading, and fail on a listed heading the pinned pages don't have. Leave the field out of the fingerprint while it's unset (D3, D5). Verify with seed loader and reader tests for spec `Sections left out`, and check that an existing season's fingerprint is unchanged.
- [ ] 1.3 Add `wikipedia_qids` to the season seed. Resolve those titles before the QID lookup, and fail on an entry no box links. Leave the field out of the fingerprint while it's unset (D4, D5). Verify with a reader test for the spec scenario `Club article that doesn't exist`, and one for a stale entry.
- [ ] 1.4 Make `just wikipedia-pins` read seeded seasons with their `wikipedia_skip` and `wikipedia_qids`, so its diff matches what sync stores. Verify with a test.

## 2. Cup Winners' Cup and UEFA Cup

- [ ] 2.1 Add the UEFA Cup Winners' Cup competition (Q40241, `TOURNAMENT`) (D1). Verify that the seeds load.
- [ ] 2.2 Generate the missing clubs from Wikidata and review them by hand into `seeds/teams.yaml` (D6). Verify that every QID the pinned boxes link resolves.
- [ ] 2.3 Pin the Cup Winners' Cup's 39 seasons and the Europa League's 49, from 1971-72 to 2019-20, with `wikipedia_skip` for the qualifying and preliminary rounds from 1994-95 and `wikipedia_qids` for 1996-97 (D1, D3, D4). Verify the counts in a sync against the spike, minus the skipped rounds, and that no stage is `FINAL` except the finals.
- [ ] 2.4 Add the awarded entries, each confirmed from a source (D7). Verify that a sync logs no awarded match missing from the seed.
- [ ] 2.5 Add the Europa League group-stage eras from 2004, cited, and compare every computed group table with Wikipedia's once, without storing anything (D8). Record the result in the PR and explain any difference.
- [ ] 2.6 Add the README coverage rows (the Cup Winners' Cup, and the Europa League from 1971-72), the sources table and the note that these seasons aren't verified. Update the `openspec/config.yaml` context. Verify that mdformat leaves no changes.

## 3. Integration

- [ ] 3.1 Run a full local sync from an empty Wikipedia cache, and then a second one. Verify that the first fetches each pin once and logs no warnings, and that the second skips every season without a request to Wikipedia.
- [ ] 3.2 Verify that `just typecheck`, `just test` and `openspec validate cup-winners-cup-and-uefa-cup-from-wikipedia --strict` all pass.

## Workflow follow-up

- Implement in two PRs: the reader (1), then the seasons and docs (2).
- Open the PRs without describing any deployment.
- Archive this change once the last PR is merged.
