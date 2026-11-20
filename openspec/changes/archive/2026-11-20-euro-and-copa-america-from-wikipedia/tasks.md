# Tasks

## 1. Reader

- [x] 1.1 Widen the stage rules: `third[- ]place` and `\bfinals?\b` (design D2). Verify with `normalize_stage` tests: `Third-place match` is `THIRD_PLACE`, `Knockout stage / Finals` is `FINAL`, and `Semi-finals` stays `SF`. Sync every openfootball season before and after, and check that no stored stage changes. Outcome: of 213 openfootball round labels, one changes. `Third-place play-off` (World Cup 2006 and 2010, Copa América 2011) was `PLAYOFF` and is now `THIRD_PLACE`, which fixes those three matches.
- [x] 1.2 Add `wikipedia_rounds` to the season seed, valid only with `wikipedia_source`. Replace a listed heading with its label, and fail on a listed heading the pinned pages don't have. Leave the field out of the fingerprint while it's unset (D3, D5). Verify with seed loader and reader tests for the spec `Headings renamed to rounds`. Also check that `Results / Play-off` becomes `Group stage`, and that an existing season's fingerprint is unchanged.
- [x] 1.3 Add `wikipedia_abandoned` to the season seed. Store the listed match `CANCELLED` without a score, and fail on an entry no box holds. Leave the field out of the fingerprint while it's unset (D4, D5). Verify with a reader test for the spec scenario `1916 Argentina v Uruguay`, and one for a stale entry. Outcome: sync merged the abandoned match into its replay as the same game rescheduled. A `CANCELLED` listing now counts as a game of its own (`matches` delta). No openfootball season lists a cancelled match and then the same pairing again. A sync test checks occurrences 1 and 2 and a table where each team has played 3. Each entry also takes a `reason`, as `awarded.yaml` entries do.
- [x] 1.4 Make `just wikipedia-pins` read seeded seasons with their `wikipedia_rounds` and `wikipedia_abandoned`, so its diff matches what sync stores. Verify with a test.

## 2. Euro and Copa América

- [x] 2.1 Add the CIS (Q721418) to `seeds/teams.yaml` (D6). Verify that every QID the pinned boxes link resolves.
- [x] 2.2 Pin Euro 1984 and 1992 and remove the seed comment about left-out editions (D1). Verify that each has 15 matches, every one with a date, and the stages `GROUP` (groups 1 and 2), `SF` and `FINAL`.
- [x] 2.3 Pin the 45 Copa América editions with `wikipedia_rounds` for the round robins and for 1989 and 1991, and `wikipedia_skip: [Qualifying round]` for 1967 (D1, D3). Search the pinned pages for "abandoned" and add a `wikipedia_abandoned` entry for each case, starting with 1916 (D4). Verify the match counts in a sync against the spike, minus 1967's qualifying round. Check that `FINAL` holds only finals, final legs and final play-offs. Outcome: 784 matches. That's the spike's count minus 1967's four qualifiers. `FINAL` holds 19 matches: the single finals, the 1983 legs, and the 1975 and 1979 legs and play-offs. Only 1916 was abandoned and replayed. The other matches the pages call abandoned or suspended kept their result (1922, 1937, 1957, 1975, 1999), or were awarded (1953 twice).
- [x] 2.4 Add the Copa América eras from 1916, cited (D7). Compare every computed group table of both competitions' new seasons with Wikipedia's once, without storing anything. Record the result in the PR and explain any difference. Outcome: 82 of 82 tables match (4 Euro, 78 Copa América). The round robins have no tie-breaker: the pages say there was none, and Wikipedia ranks level teams joint (1922, 1926, 1953). Three awarded matches go in `awarded.yaml` and as `standings.yaml` awards: 1953 Peru v Paraguay and Chile v Bolivia, and 1942 Argentina v Chile. The 1942 box doesn't say the match was awarded, so `awarded.yaml` now flags matches in box seasons too (D9).
- [x] 2.5 Update the README: the coverage rows (the Euro from 1960 with no gap, the Copa América from 1916), the note on the Euro gap, the sources table and the note that these seasons aren't verified. Update the `openspec/config.yaml` context. Verify that mdformat leaves no changes.

## 3. Integration

- [x] 3.1 Run a full local sync from an empty Wikipedia cache, then a second one. Verify that the first fetches each pin once and logs no warnings, and that the second skips every season without a request to Wikipedia. Outcome: the full sync re-synced every season except the 48 Copa América ones, which had already synced with this code. A `--full` sync of the Copa América then fetched its pins. The cache holds all 431 pinned revisions, each once, and no other. The only error line was the existing Wikidata rate-limit notice. The second sync skipped all 512 seasons in 14 seconds and wrote nothing to the cache.
- [x] 3.2 Verify that `just typecheck`, `just test` and `openspec validate euro-and-copa-america-from-wikipedia --strict` all pass. Outcome: 456 tests pass.

## Workflow follow-up

- Implement in two PRs: the reader (1), then the seasons and docs (2).
- Open the PRs without describing any deployment.
- Archive this change once the last PR is merged.
