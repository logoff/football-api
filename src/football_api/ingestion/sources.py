"""Checkout of the openfootball repositories the competition seeds reference."""

import logging
import subprocess
from pathlib import Path
from typing import Any

from football_api.domain.enums import License, Publisher
from football_api.ingestion.seeds import CompetitionSeed, SeasonSource

log = logging.getLogger(__name__)

GITHUB = "https://github.com/openfootball"


def season_files(season: SeasonSource) -> list[str]:
    """Every openfootball file a season reads: its text file, then the JSON mirror, events and squads."""
    paths = [season.file, *(p for p in (season.json_file, season.events) if p)]
    if season.squads:
        paths += season.squads.files
    return paths


def repos_for(competitions: list[CompetitionSeed]) -> list[str]:
    return sorted({p.split("/", 1)[0] for comp in competitions for season in comp.seasons for p in season_files(season)})


def openfootball_source(season: SeasonSource) -> dict[str, Any]:
    """The season's `source` (season-sources): openfootball, CC0, and a GitHub link to each file it reads."""
    pages = [{"title": p, "url": f"{GITHUB}/{p.split('/', 1)[0]}/blob/master/{p.split('/', 1)[1]}"} for p in season_files(season)]
    return {"publisher": Publisher.OPENFOOTBALL.value, "license": License.CC0.value, "pages": pages}


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True, text=True)


def ensure_sources(sources: Path, competitions: list[CompetitionSeed]) -> None:
    """Clone missing repositories and fast-forward existing ones to the latest commit.

    If a refresh fails (e.g. offline) but a checkout exists, sync continues with it.
    """
    sources.mkdir(parents=True, exist_ok=True)
    for repo in repos_for(competitions):
        target = sources / repo
        try:
            if not target.exists():
                _git("clone", "--quiet", "--depth", "1", f"{GITHUB}/{repo}.git", str(target))
            else:
                _git("-C", str(target), "fetch", "--quiet", "--depth", "1", "origin")
                _git("-C", str(target), "reset", "--quiet", "--hard", "FETCH_HEAD")
        except subprocess.CalledProcessError as exc:
            if not target.exists():
                raise
            log.warning("could not refresh %s (%s); using existing checkout", repo, exc.stderr.strip())
