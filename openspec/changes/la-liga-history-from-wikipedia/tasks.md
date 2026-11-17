# Tasks

## 1. Matches without a date

- [x] 1.1 Make `match.kickoff_utc` nullable with an Alembic migration, and add the expression index on `(coalesce(kickoff_utc, <sentinel>), id)` (design D1, D2). Verify that `just migrate` upgrades, and that the downgrade succeeds on today's data.
- [x] 1.2 Make `ParsedMatch.day` optional. Sync stores a null kickoff, sets no `original_kickoff_utc` for it, and gives `season.starts_on` and `ends_on` from dated matches only, or null (D1). Verify with sync tests on a fixture season without dates and one with a mix.
- [x] 1.3 Sort and page `/v1/matches` and the GraphQL connection on the coalesced key, and leave dateless matches out of `from` and `to` (D2). Verify with API tests for spec scenarios `Matches without a date sort last` and `Date range leaves out matches without a date`.
- [x] 1.4 Make `kickoff_utc` nullable in the REST schemas and GraphQL types, regenerate `schema.graphql`, and add a README note on dateless matches (D1). Verify that the OpenAPI and GraphQL schemas mark it nullable, and that mdformat leaves no changes.
- [x] 1.5 Make the standings sorts handle a null kickoff, and refuse `as_of` with 422 for a season with dateless matches (D3). Verify with tests for spec scenarios `Season without dates` and `Past date on a season without dates`, and check that today's standings tests still pass.

## 2. Results grids as a Wikipedia source

- [x] 2.1 Add `parse_season_grids`: every grid with its heading path, and cells paired by position (D4). Verify with parser tests on fixture HTML: one grid, several grids with headings, 1946-47's row and column names, an empty cell, and a row and column with different titles at one position. Check that `parse_results_grid`'s output is unchanged for the existing verification tests.
- [x] 2.2 Add the optional season field `wikipedia_grids`, valid only with `wikipedia_source` in a `LEAGUE` competition, and add it to the fingerprint (D4). Verify with seed loader tests for each rejected combination.
- [x] 2.3 Read grids in `read_season` for `LEAGUE` competitions: section selection, round labels `League` and `<Name> group`, `normalize_stage` and `group_of` for `<Name> group`, `CANCELLED` for empty cells, and failures for a mismatched diagonal, several grids with no sections, or a named section with no grid (D4). Verify with reader and sync tests for the spec scenarios `League season read from its results grid`, `Row and column named differently`, `Row and column that don't match`, `Annulled match`, `Second phase in groups`, `Grid of another competition on the page` and `Several grids and no sections`. Check that `First group stage` still maps as before.
- [x] 2.4 Flag awarded matches from `seeds/awarded.yaml` in grid seasons, and fail the season on an entry that matches no pairing (D5). Verify with sync tests for spec scenario `Awarded match from the seed`, and for an entry with an unknown pairing.
- [x] 2.5 Teach `just wikipedia-pins` to diff grid cells between revisions, as it diffs boxes (Risks). Verify on `1979–80 La Liga` at two revisions in a test.

## 3. La Liga 1929 to 2011-12

- [ ] 3.1 Add the 12 unseeded clubs to `seeds/teams.yaml` from Wikidata, and add Atlético Aviación (Q16549751) under Atlético Madrid's `reference_wikidata` (D6). Verify that the seeds load and that every QID the pinned grids link resolves.
- [ ] 3.2 Pin the 80 seasons with `just wikipedia-pins`. Give 1950-51 to 1955-56 `wikipedia_grids: [Results]` and 1986-87 its four sections. Verify the counts in a full sync: 22,306 matches (1929: 90; 1946-47: 182; 1979-80: 305 `COMPLETED` and 1 `CANCELLED`; 1986-87: 306 `LEAGUE` and 90 `GROUP`), with no relegation play-off stored.
- [ ] 3.3 Find awarded matches in each season's notes, and add each one to `seeds/awarded.yaml`, confirmed from a source (D5). Verify that a sync applies every entry without failing.
- [ ] 3.4 Split the La Liga standings eras: 2-1-0 from 1929 and 3-1-0 from 1995, with tie-breakers before 1995 by era, each cited (D7). Compare every computed final table with Wikipedia's once, without storing anything, and add the deductions and orders the differences call for to `seeds/standings.yaml`. Verify with the spec scenario `Two points for a win in older La Liga seasons`. Record *n* of 80 tables agreeing in the PR, and explain each one that doesn't.
- [ ] 3.5 In the README, add the La Liga coverage row, the note that these seasons have no dates and aren't verified, and the 1986-87 second-phase caveat. Update the La Liga entry in the `openspec/config.yaml` context. Verify that mdformat leaves no changes.

## 4. Integration

- [ ] 4.1 Run a full local sync from an empty Wikipedia cache, and then a second one. Verify that the first sync fetches each new pin once and logs no warnings, and that the second sends no request to Wikipedia and skips every season.
- [ ] 4.2 Verify that `just typecheck`, `just test` and `openspec validate la-liga-history-from-wikipedia --strict` all pass.

## Workflow follow-up

- Implement in three PRs: matches without a date (1), grids as a source (2), then the seasons, rules and docs (3).
- Open the PRs without describing any deployment.
- Archive this change once the last PR is merged.
