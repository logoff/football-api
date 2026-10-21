"""Season fingerprints and the choice of seasons to verify (skip-unchanged-seasons D1, D2, D5)."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
import uuid

import pytest

from football_api import season_check, verification
from football_api.ingestion.seeds import CompetitionSeed, SeasonSource, TeamSeed
from football_api.ingestion.wikipedia import MatchBox, ResultsGrid, StandingsTable, WikipediaUnavailable
from football_api.season_check import StoredCheck, code_fingerprint, season_fingerprint, teams_fingerprint, tree_fingerprint

NOW = datetime(2026, 10, 21, 1, 0, tzinfo=UTC)


def test_tree_fingerprint_follows_every_file(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "pkg" / "b.py").write_text("y = 2\n")
    first = tree_fingerprint(tmp_path)
    assert tree_fingerprint(tmp_path) == first
    (tmp_path / "pkg" / "b.py").write_text("y = 3\n")
    assert tree_fingerprint(tmp_path) != first


def test_code_fingerprint_is_stable() -> None:
    assert code_fingerprint() == code_fingerprint()
    assert len(code_fingerprint()) == 64


def _season(competitions: list[CompetitionSeed], name: str) -> tuple[CompetitionSeed, SeasonSource]:
    seed = next(c for c in competitions if c.name == name)
    return seed, seed.seasons[-1]


def test_season_fingerprint_follows_each_input(
    fixture_competitions: list[CompetitionSeed],
    fixture_teams: list[TeamSeed],
    sources_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    teams = teams_fingerprint(fixture_teams)
    league, league_src = _season(fixture_competitions, "Premier League")
    cup, cup_src = _season(fixture_competitions, "FIFA World Cup")
    assert league_src.json_file and cup_src.events and cup_src.squads

    def fingerprints() -> tuple[str, str]:
        return (
            season_fingerprint(league, league_src, teams, sources_copy),
            season_fingerprint(cup, cup_src, teams, sources_copy),
        )

    def touch(name: str) -> None:
        path = sources_copy / name
        path.write_bytes(path.read_bytes() + b"\n")

    seen = [fingerprints()]
    assert fingerprints() == seen[0]

    touch(league_src.file)
    seen.append(fingerprints())
    touch(league_src.json_file)
    seen.append(fingerprints())
    touch(cup_src.events)
    seen.append(fingerprints())
    touch(str(sorted(sources_copy.glob(cup_src.squads.files[0]))[0].relative_to(sources_copy)))
    seen.append(fingerprints())
    league_src = league_src.model_copy(update={"wikipedia": "2024–25 Premier League"})
    seen.append(fingerprints())
    league = league.model_copy(update={"name": "FA Premier League"})
    seen.append(fingerprints())
    teams = teams_fingerprint(fixture_teams[1:])
    seen.append(fingerprints())
    monkeypatch.setattr(season_check, "code_fingerprint", lambda: "0" * 64)
    seen.append(fingerprints())

    # Each change moves exactly the fingerprints of the seasons that read that input.
    moved = [tuple(a != b for a, b in zip(before, after, strict=True)) for before, after in zip(seen, seen[1:], strict=False)]
    assert moved == [
        (True, False),  # league text file
        (True, False),  # league JSON mirror
        (False, True),  # cup events file
        (False, True),  # cup squad file
        (True, False),  # league season seed entry
        (True, False),  # league competition seed entry
        (True, True),  # team seeds
        (True, True),  # code
    ]


def test_missing_optional_file_is_part_of_the_fingerprint(
    fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed], sources_copy: Path
) -> None:
    seed, src = _season(fixture_competitions, "Premier League")
    assert src.json_file
    teams = teams_fingerprint(fixture_teams)
    before = season_fingerprint(seed, src, teams, sources_copy)
    (sources_copy / src.json_file).unlink()
    assert season_fingerprint(seed, src, teams, sources_copy) != before


class Revisions:
    """A reference that only answers revision queries."""

    def __init__(self, current: dict[str, int], error: Exception | None = None) -> None:
        self.current, self.error, self.asked = current, error, list[list[str]]()

    async def revisions(self, titles: list[str]) -> dict[str, int]:
        self.asked.append(titles)
        if self.error:
            raise self.error
        return {t: self.current[t] for t in titles if t in self.current}

    @contextmanager
    def record_pages(self) -> Generator[dict[str, int]]:
        yield {}

    async def results_grid(self, title: str) -> ResultsGrid | None:
        raise AssertionError("not fetched")

    async def match_boxes(self, title: str, *, qualifying: bool = False) -> list[MatchBox]:
        raise AssertionError("not fetched")

    async def standings(self, title: str, *, qualifying: bool = False) -> list[StandingsTable]:
        raise AssertionError("not fetched")

    async def qids(self, titles: list[str]) -> dict[str, str]:
        raise AssertionError("not fetched")


def _seasons(competitions: list[CompetitionSeed], n: int) -> list[tuple[CompetitionSeed, SeasonSource]]:
    seed = next(c for c in competitions if c.name == "Premier League")
    src = seed.seasons[0]
    return [(seed, src.model_copy(update={"label": f"{2000 + i}-{i + 1:02}", "wikipedia": f"Article {i}"})) for i in range(n)]


def _checked(days_ago: float, revisions: dict[str, int], fingerprint: str = "f") -> StoredCheck:
    return StoredCheck(uuid.uuid4(), 1, fingerprint, revisions, fingerprint, NOW - timedelta(days=days_ago))


async def _due(
    seasons: list[tuple[CompetitionSeed, SeasonSource]],
    stored: dict[tuple[str, str], StoredCheck],
    reference: Revisions,
    changed: set[tuple[str, str]],
) -> set[str]:
    due = await verification._due(seasons, stored, reference, changed, NOW)  # pyright: ignore[reportPrivateUsage]
    return {label for _, label in due}


async def test_due_for_each_reason(fixture_competitions: list[CompetitionSeed]) -> None:
    seasons = _seasons(fixture_competitions, 7)
    qid = seasons[0][0].wikidata
    labels = [src.label for _, src in seasons]
    stored = {
        (qid, labels[0]): _checked(1, {"Article 0": 1}),  # re-synced in this run
        # labels[1]: never verified
        (qid, labels[2]): StoredCheck(uuid.uuid4(), 1, "new", {"Article 2": 1}, "old", NOW - timedelta(days=1)),  # data changed since
        (qid, labels[3]): _checked(1, {"Article 3": 1}),  # article edited
        (qid, labels[4]): _checked(1, {"Article 4": 1, "Article 4 Group A": 7}),  # sub-article gone or redirected away
        (qid, labels[5]): _checked(1, {"Article 5": 1, "Article 5 Group A": 7}),  # nothing changed
        (qid, labels[6]): _checked(1, {"Article 6": 1}),  # nothing changed
    }
    reference = Revisions({"Article 0": 1, "Article 2": 1, "Article 3": 2, "Article 4": 1, "Article 5": 1, "Article 5 Group A": 7, "Article 6": 1})
    due = await _due(seasons, stored, reference, {(qid, labels[0])})
    assert due == set(labels[:5])
    # One batched query, only for the seasons not already due for another reason.
    assert reference.asked == [["Article 3", "Article 4", "Article 4 Group A", "Article 5", "Article 5 Group A", "Article 6"]]


async def test_rotation_takes_old_checks_oldest_first_capped(fixture_competitions: list[CompetitionSeed]) -> None:
    seasons = _seasons(fixture_competitions, 15)
    qid = seasons[0][0].wikidata
    # Seasons 0-9 last verified 8 to 17 days ago, 10-14 yesterday.
    stored = {(qid, src.label): _checked(8 + i if i < 10 else 1, {f"Article {i}": 1}) for i, (_, src) in enumerate(seasons)}
    reference = Revisions({f"Article {i}": 1 for i in range(15)})
    assert await _due(seasons, stored, reference, set()) == {seasons[9][1].label, seasons[8][1].label, seasons[7][1].label}


async def test_unavailable_revisions_leave_only_other_reasons(
    fixture_competitions: list[CompetitionSeed], caplog: pytest.LogCaptureFixture
) -> None:
    seasons = _seasons(fixture_competitions, 2)
    qid = seasons[0][0].wikidata
    stored = {(qid, src.label): _checked(1, {f"Article {i}": 1}) for i, (_, src) in enumerate(seasons)}
    reference = Revisions({}, error=WikipediaUnavailable("HTTP 503"))
    assert await _due(seasons, stored, reference, {(qid, seasons[1][1].label)}) == {seasons[1][1].label}
    assert "edited pages aren't detected this run" in caplog.text


async def test_without_changed_every_season_is_due(fixture_competitions: list[CompetitionSeed]) -> None:
    seasons = _seasons(fixture_competitions, 3)
    stored = {(seasons[0][0].wikidata, src.label): _checked(1, {}) for _, src in seasons}
    due = await verification._due(seasons, stored, Revisions({}), None, NOW)  # pyright: ignore[reportPrivateUsage]
    assert len(due) == 3
