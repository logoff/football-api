# Tasks

## 1. Reference

- [x] 1.1 Parse the line-up table after each match box (D1): starters, substitutes who came on, numbers when present, `yel`, `sent off`/`sentoff`, `suboff` and `subon` templates from `data-mw`. Verify with tests on hand-written tables in each format (with and without shirt numbers, a wrapped side table, every template), and by parsing every page the verifier reads: 1,202 tables, 2,404 sides of eleven starters.
- [x] 1.2 Take the table from whichever copy of a box has one in `merge_boxes`. Verify with a test on a season article plus a group sub-article.
- [x] 1.3 Skip red links in `parse_subarticle_titles`. Verify with a test on the 1998 World Cup article.

## 2. Comparison

- [x] 2.1 Pair players within a side (D3). Verify with tests for each rule and for an unpaired player.
- [x] 2.2 Compare a match's events and compute its status (D2), including the 1970 rule, the one-minute tolerance, added minutes and second yellows. Verify with a test per scenario in the spec.

## 3. Storage, reports and API

- [x] 3.1 Add `aspect` to `match_verification` with its migration (D4). Verify that existing rows become `RESULT` and that the migration downgrades.
- [x] 3.2 Store events statuses, log the disagreement and summary lines, and report skipped seasons' stored events statuses (D5). Verify that `tools/verify_report.py` reads the new lines.
- [x] 3.3 Add `events_verification` to match responses and the filter (D6). Verify with API tests.

## 4. Integration

- [x] 4.1 Run a full sync with `--verify` on an empty database. Record the events status counts and the time, and check a sample of mismatches by hand to split real errors from parser or rule problems.
- [x] 4.2 Verify that `just typecheck`, `just test` and `openspec validate verify-match-events --strict` pass.

## Workflow follow-up

- Infra PR: the Kuma handling of events mismatches (design, open question).
- First triage of the events mismatches: fixes upstream, name variants, known list.
- Archive this change once it's merged.
