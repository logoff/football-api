"""Typed loaders for the hand-curated seed files under `seeds/`."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from football_api.domain.enums import CompetitionFormat, CompetitionScope, TeamKind
from football_api.infra.settings import get_settings


class _Seed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SquadSource(_Seed):
    style: Literal["more", "per-team"]
    files: list[str]


class SeasonSource(_Seed):
    label: str
    start_year: int
    file: str
    tz: str = Field(description="IANA zone of the file's kickoff times, or `inline`")
    json_file: str | None = Field(default=None, alias="json")
    squads: SquadSource | None = None
    wikipedia: str | None = Field(
        default=None, description="English Wikipedia article whose results grid verifies this season"
    )


class CompetitionSeed(_Seed):
    name: str
    country: str | None = None
    team_kind: TeamKind
    scope: CompetitionScope
    format: CompetitionFormat
    wikidata: str = Field(description="Wikidata QID; the competition's identity across syncs")
    seasons: list[SeasonSource] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_labels(self) -> "CompetitionSeed":
        labels = [s.label for s in self.seasons]
        if len(labels) != len(set(labels)):
            raise ValueError(f"{self.name}: duplicate season label")
        return self


class TeamSeed(_Seed):
    name: str
    kind: TeamKind
    country: str | None
    wikidata: str | None = None
    openfootball: list[str] = Field(min_length=1)


def _load(path: Path) -> object:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_competitions(path: Path | None = None) -> list[CompetitionSeed]:
    data = _load(path or get_settings().seeds_dir / "competitions.yaml")
    competitions = TypeAdapter(list[CompetitionSeed]).validate_python(data)
    qids = [c.wikidata for c in competitions]
    if len(qids) != len(set(qids)):
        raise ValueError("duplicate Wikidata QID in competitions.yaml")
    return competitions


def load_teams(path: Path | None = None) -> list[TeamSeed]:
    data = _load(path or get_settings().seeds_dir / "teams.yaml")
    teams = TypeAdapter(list[TeamSeed]).validate_python(data)
    seen_qids: dict[str, str] = {}
    seen_aliases: dict[str, str] = {}
    for team in teams:
        if team.wikidata:
            if team.wikidata in seen_qids:
                raise ValueError(f"Wikidata {team.wikidata} listed under both {seen_qids[team.wikidata]} and {team.name}")
            seen_qids[team.wikidata] = team.name
        for alias in team.openfootball:
            if alias in seen_aliases:
                raise ValueError(f"openfootball alias {alias!r} listed under both {seen_aliases[alias]} and {team.name}")
            seen_aliases[alias] = team.name
    return teams
