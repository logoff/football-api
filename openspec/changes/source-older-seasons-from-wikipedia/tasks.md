# Tasks

## 1. Source and license model

- [x] 1.1 Add `season.source` (JSON) with an Alembic migration that backfills openfootball and `CC0-1.0` (design D7). Verify that `just migrate` upgrades and downgrades cleanly.
- [x] 1.2 Fill `season.source` in sync for openfootball seasons, with the GitHub URL of every file read. Verify with tests.
- [x] 1.3 Serve `source` on seasons and `license` on matches in REST and GraphQL, and regenerate `schema.graphql`. Verify with API and GraphQL tests.

## 2. Wikipedia as a season source

- [x] 2.1 Add `wikipedia_source` pins to the season seed, exclusive with every openfootball field and with `wikipedia` (D1). Let `TeamSeed.openfootball` be empty when there is a QID (D5). Verify with seed loader tests for each rejected combination.
- [x] 2.2 Fetch pinned revisions and cache their HTML and resolved QIDs under `SOURCES_DIR/wikipedia/` (D2, D5). Verify with client tests on a mock transport that a second read sends no request, and that a failed fetch raises the source error.
- [x] 2.3 Give each match box its heading path, and add the stage rules the spike found (D3). Verify with parser tests on fixture HTML: numbered rounds, groups, two group stages, replays, and an unknown heading that fails.
- [x] 2.4 Turn boxes into parsed matches, keyed by QID, with walkovers `CANCELLED` and awarded boxes flagged (D3, D4). Sync Wikipedia seasons through them, add the pins to the fingerprint, and teach `phase_of` the second group stage. Verify with sync tests on a fixture season: stored matches, an unknown QID that fails, and a moved pin that re-syncs only that season.
- [x] 2.5 Add `just wikipedia-pins` with the box diff between revisions, and the discovery fix for other competitions and sports, applied to verification too (D6). Verify on `1960–61 European Cup` that the Winners' Cup article isn't pinned.

## 3. European Cup and Champions League 1955-56 to 2010-11

- [ ] 3.1 Generate the 189 missing clubs from Wikidata and review them by hand into `seeds/teams.yaml` (D5). Verify that the seeds load and that every QID the pinned boxes link resolves.
- [ ] 3.2 Pin the 56 seasons with `just wikipedia-pins`. Verify that each season's match count matches the spike (4,321 in all; 1955-56: 29), and that no pinned page belongs to another competition.
- [ ] 3.3 Add the 5 awarded entries to `seeds/awarded.yaml`, each confirmed from a source (D4). Verify that a sync logs no awarded match missing from the seed.
- [ ] 3.4 Add the Champions League standings eras for the group stages from 1991-92, cited from the regulations of the time (D8). Verify by comparing the computed group tables with Wikipedia's, once and without storing anything. Explain any difference in the PR.

## 4. Docs

- [ ] 4.1 In the README, add the data sources and license section (spec `Attribution and share-alike`), the Champions League coverage row, the note that Wikipedia seasons aren't verified, and the walkover note. Update the `openspec/config.yaml` context and the `ingestion` spec's Purpose. Verify that mdformat leaves no changes.

## 5. Integration

- [ ] 5.1 Run a full local sync from an empty cache, and then a second one. Verify that the first one fetches each pin once and logs no warnings, and that the second one sends no request to Wikipedia and skips every season.
- [ ] 5.2 Verify that `just typecheck`, `just test` and `openspec validate source-older-seasons-from-wikipedia --strict` all pass.

## Workflow follow-up

- Implement in several PRs: the model (1), the source (2), and then the seasons and docs (3, 4).
- Open the PRs without describing any deployment.
- Archive this change once the last PR is merged.
