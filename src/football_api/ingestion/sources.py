"""Checkout of the openfootball repositories the competition seeds reference."""

import logging
import subprocess
from pathlib import Path

from football_api.ingestion.seeds import CompetitionSeed

log = logging.getLogger(__name__)

GITHUB = "https://github.com/openfootball"


def repos_for(competitions: list[CompetitionSeed]) -> list[str]:
    repos: set[str] = set()
    for comp in competitions:
        for season in comp.seasons:
            paths = [season.file, *([season.json_file] if season.json_file else [])]
            if season.squads:
                paths += season.squads.files
            repos |= {p.split("/", 1)[0] for p in paths}
    return sorted(repos)


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
