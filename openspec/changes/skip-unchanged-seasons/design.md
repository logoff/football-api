# Design

## Context

`run_sync` clones the openfootball repositories, writes the seeds, checks Wikidata, then syncs every season in its own transaction and, with `--verify`, verifies every synced season that names a Wikipedia article. Nothing is remembered between runs, so every night repeats the whole history.

Timings of the last two nightly runs (227 seasons):

| Phase                  | 2026-10-20 | 2026-10-21 |
| ---------------------- | ---------: | ---------: |
| Clone, seeds, Wikidata |       0:30 |       0:38 |
| Sync                   |       5:00 |       6:22 |
| Verification           |      15:30 |      21:00 |
| **Total**              |  **21:00** |  **28:00** |

How often the 225 season articles change, measured on 2026-10-21:

| Window | Edited (new revision) | `touched` (re-rendered) |
| ------ | --------------------: | ----------------------: |
| 1 day  |                     5 |                      63 |
| 2 days |                    12 |                      86 |
| 7 days |                    67 |                     145 |

`touched` also moves when any included template is edited, flag icons included, so it would trigger re-checks on a quarter of the seasons every night.

The sync doesn't depend on the current date: the same inputs always produce the same rows. That's what makes skipping safe.

## Goals / Non-Goals

**Goals:**

- A nightly run that only re-processes what changed, without missing an upstream correction, a seed change, a code change or a Wikipedia edit.
- The same logs and reports as today: every season is counted, and an unreviewed mismatch is flagged every night until it's listed.

**Non-Goals:**

- Skipping the clone. A shallow clone takes seconds, and the files are needed to compute fingerprints.
- Caching inside a season, such as re-syncing only the changed matches. A season stays the unit of work and of transaction.
- Making the GitHub workflow incremental. Its job is a full rebuild from an empty database.

## Decisions

### D1. Season fingerprint

A SHA-256 over, in order:

1. the code fingerprint (D2);
1. the competition's seed entry without its `seasons` list, and this season's entry, as canonical JSON;
1. the team seeds from `seeds/teams.yaml`, as canonical JSON of the parsed entries, since team spellings decide how every name resolves;
1. the path and bytes of every file the season's sync reads: the text file, the JSON mirror, the events file and every squad file the patterns match. An optional file that is missing is hashed as missing.

The file list comes from the same functions that read the files, so the fingerprint can't miss a file the parser reads.

After a season syncs successfully, its fingerprint is stored in the same transaction. A failed season stores nothing, so it is retried on the next run.

**Alternative:** the openfootball repository's commit SHA. Rejected, because a commit to any file of a repository would re-sync every season in it.

### D2. Code fingerprint

A SHA-256 of the installed `football_api` package's `.py` files, in sorted path order. It works the same in the image, in CI and locally, and needs no build arguments.

Every code change, including API-only ones, makes the next run a full run. That's at most one full run per night, and it can't miss a change that alters what the sync writes.

**Alternatives:**

- The image's git commit SHA. Rejected: the image doesn't carry it today, and local runs have none.
- Hashing only the ingestion and verification modules. Rejected for now: a change elsewhere (an enum, a model) can change what the sync writes, and getting that list wrong would silently skip seasons. It can be narrowed later if full runs after deploys become a problem.

### D3. `season_check` table

One row per season, internal and not exposed in the API:

| Column                  | Type                                      | Meaning                                                                                                                  |
| ----------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `season_id`             | UUID, PK, FK → `season` ON DELETE CASCADE |                                                                                                                          |
| `source_fingerprint`    | text                                      | D1, at the last successful sync                                                                                          |
| `synced_at`             | timestamptz                               | time of that sync                                                                                                        |
| `reference_revisions`   | JSONB, nullable                           | `{title: revision_id}` of every Wikipedia page the last complete verification read                                       |
| `reference_fingerprint` | text, nullable                            | the `source_fingerprint` that verification checked                                                                       |
| `unpaired`              | integer, nullable                         | stored matches no match box paired with, at that verification (cups and tournaments), for the report of a skipped season |
| `verified_at`           | timestamptz, nullable                     | time of the last complete verification                                                                                   |

Revision IDs and titles are metadata about the reference, not reference content, so the "never stored" requirement is amended to allow them (spec delta).

### D4. Recording revision IDs

The Wikipedia REST `page/html` response carries the page's revision in its `content-revision-id` header, which matches the action API's `lastrevid`. The client records it with every page it fetches, at no extra request. Verification collects the titles and revision IDs of every page read for one season: the article, its sub-articles, and the standings pages. After a complete verification they are stored with `verified_at` and `reference_fingerprint`.

A sub-article that can't be fetched isn't recorded, so the next run doesn't depend on it. A new sub-article link is an edit to the article, so it changes the article's revision.

The current revision IDs come from the action API, `prop=info` with `redirects=1`, 50 titles per request: about 17 requests for the whole run. A title that now redirects elsewhere or no longer exists counts as changed.

### D5. When a season is verified

With `--verify` and without `--full`, a season that names an article is verified when any of these holds:

1. it was synced in this run (its data changed);
1. it has no complete verification stored, or `reference_fingerprint` differs from `source_fingerprint`;
1. any page in `reference_revisions` has a different current revision;
1. its last complete verification is more than 7 days old, and it is among the `ceil(n / 7)` such seasons with the oldest `verified_at`, where `n` is the number of seasons in this run that name an article.

Rule 4 is a rotation. Every season is re-checked about once a week, even when nothing visible changed. That catches what revision IDs can't show: edits to an included template, and a team article that now links a different Wikidata item. The cap of a seventh per run spreads the load: after a full run, nothing rotates for a week, then the seasons come due over the following week and stay spread from then on. A season can then wait up to about two weeks once, right after a full run.

**Alternative:** always re-check the seventh with the oldest checks. Rejected: it re-checks seasons verified the night before, after every full run, and at least one season on every run, however recent.

A verification that can't complete (reference unavailable, no grid or boxes) stores nothing, so the season is tried again on the next run.

### D6. Reporting skipped seasons

A season whose sync is skipped logs `<competition> <season>: unchanged, <n> matches`.

A season whose verification is skipped logs the same summary line as today, computed from its stored statuses and its stored `unpaired` count, with `unchanged` at the end:

```text
INFO Premier League 2015-16: verified against wikipedia: VERIFIED=380 MISMATCH=0 UNCONFIRMED=0 SOURCE_BEHIND=0 unchanged
```

It also logs one line per stored `MISMATCH` and `SOURCE_BEHIND` match and table row, in today's format up to `stored`, with the stored side and the date of the last check instead of the reference's value, which isn't stored:

```text
WARNING CONMEBOL Copa Libertadores 2015: MISMATCH Boca Juniors v CA River Plate: stored 0–3, wikipedia unchanged since 2026-10-21
```

The nightly report script (`report.py`) and `tools/verify_report.py` match these lines up to `stored`, so they keep counting every season and keep reporting a new mismatch every night until it's listed. A known mismatch in a skipped season isn't reported as gone.

### D7. `--full` and the GitHub schedule

`--full` ignores `season_check`: every season is synced and every season with an article verified, and their rows are rewritten. Nothing else changes from today's behaviour.

The GitHub workflow starts from an empty database, so it has no stored fingerprints and always runs fully without the flag. Its schedule moves from daily to weekly (Sundays, 03:00 UTC). It still runs on merges to `main` that touch code, seeds or migrations, and by hand. A failure to rebuild from scratch only appears after a code, seed or migration change, which merges already cover. A new openfootball file that breaks parsing also fails production's sync, because a changed file is re-synced there.

## Expected nightly cost

| Night                        | Sync                        | Verification                                     | Total             |
| ---------------------------- | --------------------------- | ------------------------------------------------ | ----------------- |
| No deploy since the last run | ~25 changed seasons, ~1 min | changed + edited + rotation, ~60 seasons, ~5 min | ~7 min            |
| After a deploy               | every season                | every season                                     | ~25 min, as today |

The rotation is most of the verification cost. Its period is one constant; a longer period makes routine nights cheaper but takes longer to notice a template-only edit.

## Integration run

On an empty local database, with every competition and the same openfootball checkout throughout:

1. `--verify`: 227 seasons synced and verified in 11 min 20 s (18 min 40 s on a first try with a slower Wikipedia). One mismatch, Boca v River 2015.
1. `--verify` again: 8.9 s. All 227 seasons were logged as unchanged, 0 were due for verification, and `tools/verify_report.py` gave the same totals, table counts and disagreements as the first run, Boca v River included.
1. One source file changed (Serie A 2015-16) and one stored revision edited (Ligue 1 2019-20), then `--verify`: 14 s. Only Serie A 2015-16 was re-synced, and exactly those two seasons were verified again.

## Risks / Trade-offs

- **[Risk] A Wikipedia change with no new revision on any recorded page** (an included template edited). → The rotation re-checks every season at least about weekly; `--full` forces it immediately.
- **[Risk] The fingerprint misses an input.** → The file list comes from the same functions that read the files, the code fingerprint covers the whole package, and the GitHub workflow's weekly full rebuild from scratch would show a difference from production. Tests cover each input changing on its own.
- **[Trade-off] Every deploy makes the next night a full run.** → Accepted; the nightly job's deadline is now an hour.
- **[Trade-off] `checked_at` of a skipped season is the last real comparison, not last night.** → That's what it means today too; the API documentation says so.
