# Proposal

## Why

La Liga is the first competition to grow past v0.1, and two things hold it back. Its data comes from one volunteer-maintained source with nothing checking it, and it only has 2024-25: eleven earlier seasons openfootball already has are missing, so is the season in progress, and nothing refreshes it. The official sources (RFEF, LaLiga) sell their data and don't allow reuse, so trust has to come from two independent open sources agreeing, and freshness from a sync that runs on a schedule.

## What Changes

- **Cross-check against Wikipedia.** Every La Liga match score from openfootball is compared with the results grid of the English Wikipedia season article. openfootball (CC0) remains the only data source. Wikipedia (CC BY-SA) is read only to compare, and nothing from it is stored or served.

- **Verification status per match:**

  - `VERIFIED`: both sources have the same score.
  - `MISMATCH`: the scores differ.
  - `UNCONFIRMED`: openfootball has a score Wikipedia doesn't have yet.
  - `SOURCE_BEHIND`: Wikipedia has a score openfootball lacks.

  The status is shown on matches in the API and can be filtered on. Disagreements are reported and never resolved automatically.

- **Several seasons per competition.** Seeds can list several seasons for a competition. La Liga covers every season openfootball has: the 15 seasons from 2012-13 to 2026-27, the season in progress. **BREAKING (seeds file format):** `season:` becomes a list named `seasons:` for every competition. The other 12 keep their single season.

- **Teams.** Every club that played La Liga from 2012-13 onwards and isn't seeded yet is added to `seeds/teams.yaml` with their Wikidata QIDs.

- **Scheduled sync.** The sync command can be limited to some competitions (by Wikidata QID) and can run verification afterwards. Its exit codes and log output let an external scheduler run it unattended.

- **Container image.** The image can run that scheduled sync, so it now ships `git`. The sources directory is configurable so it can point to a writable volume.

## Capabilities

### New Capabilities

- `match-verification`: compares stored match results with an independent open reference, gives each match a verification status, and reports disagreements without changing data.

### Modified Capabilities

- `catalog`: Season catalog. A competition can be ingested for several seasons, including one in progress, not only the last completed one.
- `ingestion`: the sync can be limited to selected competitions and can run verification, for unattended scheduled runs.

## Impact

- **Code:**
  - `ingestion/seeds.py`: the `seasons` list.
  - `sync.py`: CLI options and a loop over seasons.
  - A new Wikipedia results-grid reader and verification module.
  - API schemas and `/v1/matches`: the `verification` field and filter.
- **Database:** an Alembic migration adds a per-match verification table.
- **Seeds:** `competitions.yaml` (format change, La Liga seasons) and `teams.yaml` (promoted clubs).
- **Dependencies:** an HTML parser (BeautifulSoup) for the rendered Wikipedia grid. `httpx` is already present.
- **Image:** `git` in the runtime stage.
- **Network:** each verification run makes about two requests per La Liga season (about 30 for the 15 seasons) to the Wikipedia REST and Action APIs, identified by a project User-Agent with no personal contact details.
- **Out of scope:** where and how the schedule runs. Deployment manifests live outside this repo.
