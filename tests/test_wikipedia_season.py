"""Wikipedia as a season source: headings, pinned revisions and their cache, boxes to matches
(ingestion spec: Wikipedia season source, Pinned revisions are cached, Stage from section headings,
Walkovers; design D2–D5)."""

from collections.abc import Iterable
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from football_api.domain.enums import DecidedBy, EntityType, MatchStatus, Stage, TeamKind
from football_api.infra.db import get_sessionmaker
from football_api.infra.models import ExternalRef, Match, Season, Team, TeamSeason
from football_api.ingestion.openfootball.text_parser import normalize_stage
from football_api.ingestion.seeds import CompetitionSeed, SeasonSource, TeamSeed, WikipediaPin
from football_api.ingestion.wikipedia import WikipediaUnavailable, parse_match_boxes, parse_subarticle_titles
from football_api.ingestion.wikipedia_season import (
    RevisionStore,
    WikipediaSourceError,
    read_season,
    round_label,
    seeded_qids,
    source_of,
)
from football_api.standings import group_of, phase_of
from football_api.sync import SyncReport, run_sync
from football_api.wikipedia_pins import box_diff, pins_yaml, rows


def club(name: str) -> str:
    return f'<a href="./{name.replace(" ", "_")}" title="{name}">{name}</a>'


def box(day: str, home: str, away: str, score: str) -> str:
    return (
        f'<div class="footballbox"><div class="fdate"><span class="dtstart">{day}</span></div>'
        f'<table class="fevent"><tbody><tr><th class="fhome">{club(home)}</th><th class="fscore">{score}</th>'
        f'<th class="faway">{club(away)}</th></tr></tbody></table></div>'
    )


def section(heading: str, *content: str, level: int = 2) -> str:
    return f'<section><div class="mw-heading mw-heading{level}"><h{level}>{heading}</h{level}></div>{"".join(content)}</section>'


MAIN = "1960–61 European Cup"
MAIN_HTML = (
    "<html><head><title>1960–61 European Cup</title></head><body>"
    + section(
        "First round",
        section("First leg", box("1960-09-14", "Alpha F.C.", "Beta F.C.", "2–1"), level=3),
        section("Second leg", box("1960-09-28", "Beta F.C.", "Alpha F.C.", "1–0"), level=3),
        section("Play-off", box("1960-10-05", "Alpha F.C.", "Beta F.C.", "3–2 (a.e.t.)"), level=3),
    )
    + section(
        "Quarter-finals",
        section("First leg", box("1961-01-18", "Gamma F.C.", "Delta F.C.", "w/o"), level=3),
        section("Second leg", box("1961-02-01", "Delta F.C.", "Gamma F.C.", "0–3 (awd.)"), level=3),
    )
    + section("Final", box("1961-05-31", "Alpha F.C.", "Gamma F.C.", "1–1 (4–3 p)"))
    + "</body></html>"
)
GROUPS = f"{MAIN} second group stage"
GROUPS_HTML = section("Groups", section("Group B", box("1961-03-01", "Beta F.C.", "Delta F.C.", "2–2"), level=3))
QIDS = {"Alpha F.C.": "Q1", "Beta F.C.": "Q2", "Gamma F.C.": "Q3", "Delta F.C.": "Q4"}


class FakeWikipedia:
    def __init__(self, pages: dict[tuple[str, int], str], qids: dict[str, str]) -> None:
        self.pages, self.qid_map = pages, qids
        self.requests: list[str] = []

    async def revision_html(self, title: str, revision: int) -> str:
        self.requests.append(f"html {title} {revision}")
        if (title, revision) not in self.pages:
            raise WikipediaUnavailable(f"{title} revision {revision}: HTTP 404")
        return self.pages[(title, revision)]

    async def qids(self, titles: Iterable[str]) -> dict[str, str]:
        titles = list(titles)
        self.requests.append(f"qids {len(titles)}")
        return {t: self.qid_map[t] for t in titles if t in self.qid_map}


def season(*pins: tuple[str, int]) -> SeasonSource:
    return SeasonSource.model_validate(
        {"label": "1960-61", "start_year": 1960, "wikipedia_source": [{"title": t, "revision": r} for t, r in pins]}
    )


def fake() -> FakeWikipedia:
    return FakeWikipedia({(MAIN, 100): MAIN_HTML, (GROUPS, 200): GROUPS_HTML}, QIDS)


def test_boxes_carry_their_section_headings() -> None:
    boxes = parse_match_boxes(MAIN_HTML)
    assert [b.heading for b in boxes][:3] == [("First round", "First leg"), ("First round", "Second leg"), ("First round", "Play-off")]
    assert boxes[2].extra_time and not boxes[0].extra_time


@pytest.mark.parametrize(
    ("suffix", "heading", "label", "stage", "number"),
    [
        ("", ("First round", "First leg"), "First round", Stage.ROUND, 1),
        ("", ("Quarter-finals", "Play-off"), "Quarter-finals", Stage.QF, None),
        ("", ("Final", "Replay"), "Final", Stage.FINAL, None),
        ("", ("Preliminary round", "Second leg"), "Preliminary round", Stage.PRELIMINARY, None),
        ("first group stage", ("Groups", "Group A"), "First group stage / Group A", Stage.GROUP, None),
        ("knockout phase", ("Round of 16", "Matches"), "Round of 16", Stage.R16, None),
        ("first round", ("Matches",), "First round", Stage.ROUND, 1),
    ],
)
def test_round_label_from_page_and_headings(suffix: str, heading: tuple[str, ...], label: str, stage: Stage, number: int | None) -> None:
    assert round_label(suffix, heading) == label
    assert normalize_stage(label) == (stage, number)


def test_second_group_stage_is_phase_two() -> None:
    assert (phase_of("Second group stage / Group B"), group_of("Second group stage / Group B")) == (2, "B")
    assert phase_of("First group stage / Group B") == 1


def test_discovery_skips_other_competitions_and_sports() -> None:
    links = "".join(
        f'<a href="./{t.replace(" ", "_")}">{t}</a>'
        for t in (f"{MAIN} first round", "1960–61 European Cup Winners' Cup", "1960–61 European Cup (handball)")
    )
    assert parse_subarticle_titles(links, MAIN) == [f"{MAIN} first round"]


async def test_read_season_from_pins(tmp_path: Path) -> None:
    read = await read_season(season((MAIN, 100), (GROUPS, 200)), RevisionStore(tmp_path, fake()), {})
    got = [(m.round_label, m.day, m.home, m.away, m.status, m.score, m.awarded) for m in read.matches]
    assert [g[:4] for g in got] == [
        ("First round", date(1960, 9, 14), "Q1", "Q2"),
        ("First round", date(1960, 9, 28), "Q2", "Q1"),
        ("First round", date(1960, 10, 5), "Q1", "Q2"),
        ("Quarter-finals", date(1961, 1, 18), "Q3", "Q4"),
        ("Quarter-finals", date(1961, 2, 1), "Q4", "Q3"),
        ("Final", date(1961, 5, 31), "Q1", "Q3"),
        ("Second group stage / Group B", date(1961, 3, 1), "Q2", "Q4"),
    ]
    play_off, walkover, awarded, final = read.matches[2], read.matches[3], read.matches[4], read.matches[5]
    assert play_off.score and play_off.score.decided_by is DecidedBy.EXTRA_TIME
    assert (walkover.status, walkover.score) == (MatchStatus.CANCELLED, None)
    assert awarded.awarded and awarded.score and (awarded.score.home, awarded.score.away) == (0, 3)
    assert final.score and (final.score.decided_by, final.score.home_pens, final.score.away_pens) == (DecidedBy.PENALTIES, 4, 3)
    assert all(m.kickoff is None for m in read.matches)
    assert (read.path, read.clubs["Q1"]) == (MAIN, "Alpha F.C.")


async def test_revisions_and_qids_are_fetched_once(tmp_path: Path) -> None:
    wiki = fake()
    src = season((MAIN, 100), (GROUPS, 200))
    first = await read_season(src, RevisionStore(tmp_path, wiki), {})
    assert wiki.requests == [f"html {MAIN} 100", f"html {GROUPS} 200", "qids 4", "qids 2"]
    wiki.requests.clear()
    again = await read_season(src, RevisionStore(tmp_path, wiki), {})
    assert wiki.requests == [] and again == first


async def test_unreachable_revision_fails(tmp_path: Path) -> None:
    with pytest.raises(WikipediaUnavailable):
        await read_season(season((MAIN, 101)), RevisionStore(tmp_path, fake()), {})


async def test_unknown_heading_fails_naming_page_and_revision(tmp_path: Path) -> None:
    wiki = FakeWikipedia({(MAIN, 100): section("Trivia", box("1960-09-14", "Alpha F.C.", "Beta F.C.", "1–0"))}, QIDS)
    with pytest.raises(WikipediaSourceError, match=r"1960–61 European Cup \(revision 100\): heading 'Trivia'"):
        await read_season(season((MAIN, 100)), RevisionStore(tmp_path, wiki), {})


async def test_club_without_qid_fails(tmp_path: Path) -> None:
    wiki = FakeWikipedia({(MAIN, 100): MAIN_HTML}, {k: v for k, v in QIDS.items() if k != "Gamma F.C."})
    with pytest.raises(WikipediaSourceError, match="'Gamma F.C.' has no Wikidata QID"):
        await read_season(season((MAIN, 100)), RevisionStore(tmp_path, wiki), {})


async def test_reference_qids_fold_to_the_seeded_team(tmp_path: Path) -> None:
    teams = [TeamSeed(name="Alpha", kind=TeamKind.CLUB, country=None, wikidata="Q10", reference_wikidata=["Q1"])]
    read = await read_season(season((MAIN, 100)), RevisionStore(tmp_path, fake()), seeded_qids(teams))
    assert read.matches[0].home == "Q10"


def test_source_links_each_pinned_revision() -> None:
    assert source_of(season((MAIN, 100), (GROUPS, 200))) == {
        "publisher": "Wikipedia",
        "license": "CC-BY-SA-4.0",
        "pages": [
            {"title": MAIN, "url": "https://en.wikipedia.org/w/index.php?oldid=100"},
            {"title": GROUPS, "url": "https://en.wikipedia.org/w/index.php?oldid=200"},
        ],
    }


@pytest.mark.parametrize(
    "extra",
    [{"file": "x.txt"}, {"tz": "Europe/Madrid"}, {"json": "x.json"}, {"events": "x.txt"}, {"wikipedia": "1960–61 European Cup"}],
)
def test_wikipedia_season_excludes_other_sources(extra: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="excludes"):
        SeasonSource.model_validate({"label": "1960-61", "start_year": 1960, "wikipedia_source": [{"title": MAIN, "revision": 1}], **extra})


def test_season_needs_a_source() -> None:
    with pytest.raises(ValueError, match="needs `file` and `tz`"):
        SeasonSource.model_validate({"label": "1960-61", "start_year": 1960, "file": "x.txt"})
    with pytest.raises(ValueError, match="pinned twice"):
        season((MAIN, 1), (MAIN, 2))


def test_team_needs_a_spelling_or_a_qid() -> None:
    assert TeamSeed(name="Djurgårdens IF", kind=TeamKind.CLUB, country="SE", wikidata="Q207548").openfootball == []
    with pytest.raises(ValueError, match="spelling or a Wikidata QID"):
        TeamSeed(name="Nobody", kind=TeamKind.CLUB, country=None)



# --- sync (needs the database) --------------------------------------------------------------------

CUP = {"name": "UEFA Champions League", "team_kind": "CLUB", "scope": "CONTINENTAL", "format": "TOURNAMENT", "wikidata": "Q18756"}
CLUBS = [TeamSeed(name=n.removesuffix(" F.C."), kind=TeamKind.CLUB, country=None, wikidata=q) for n, q in QIDS.items()]


def cup(*seasons: SeasonSource) -> list[CompetitionSeed]:
    return [CompetitionSeed.model_validate({**CUP, "seasons": [s.model_dump(by_alias=True, exclude_unset=True) for s in seasons]})]


def season_of(label: str, *pins: tuple[str, int]) -> SeasonSource:
    return season(*pins).model_copy(update={"label": label, "start_year": int(label[:4])})


async def wiki_sync(competitions: list[CompetitionSeed], teams: list[TeamSeed], wiki: FakeWikipedia) -> SyncReport:
    return await run_sync(competitions=competitions, teams=teams, refresh_sources=False, wikipedia=wiki)


@pytest.mark.db
async def test_wikipedia_season_syncs_from_its_pins(fresh_db: Path, fixture_teams: list[TeamSeed]) -> None:
    report = await wiki_sync(cup(season((MAIN, 100), (GROUPS, 200))), fixture_teams + CLUBS, fake())
    assert not report.failed, report.failed
    async with get_sessionmaker()() as session:
        [row] = (await session.execute(select(Season))).scalars().all()
        assert row.source["license"] == "CC-BY-SA-4.0"
        matches = (await session.scalars(select(Match).order_by(Match.kickoff_utc))).all()
        assert len(matches) == 7
        assert {(m.stage, m.status) for m in matches} >= {(Stage.ROUND, MatchStatus.COMPLETED), (Stage.QF, MatchStatus.CANCELLED), (Stage.GROUP, MatchStatus.COMPLETED)}
        refs = set(await session.scalars(select(ExternalRef.source).where(ExternalRef.entity_type == EntityType.MATCH)))
        assert refs == {"wikipedia"}
        # Teams with no openfootball spelling took part, identified by their QIDs.
        names = set(await session.scalars(select(Team.name).join(TeamSeason).where(TeamSeason.season_id == row.id)))
        assert names == {"Alpha", "Beta", "Gamma", "Delta"}
    assert (fresh_db / "wikipedia" / "100.html").is_file()


@pytest.mark.db
async def test_unseeded_qid_fails_the_season(fresh_db: Path, fixture_teams: list[TeamSeed]) -> None:
    report = await wiki_sync(cup(season((MAIN, 100))), fixture_teams + CLUBS[:3], fake())
    [(_, _, exc)] = report.failed
    assert "unknown team 'Delta F.C. (Q4)'" in str(exc)


@pytest.mark.db
async def test_pinned_seasons_resync_only_when_a_pin_moves(fresh_db: Path, fixture_teams: list[TeamSeed]) -> None:
    wiki = fake()
    wiki.pages[(MAIN, 101)] = MAIN_HTML.replace("2–1", "2–0")
    older, newer = season_of("1959-60", (GROUPS, 200)), season_of("1960-61", (MAIN, 100))
    teams = fixture_teams + CLUBS
    assert len((await wiki_sync(cup(older, newer), teams, wiki)).synced) == 2
    wiki.requests.clear()
    again = await wiki_sync(cup(older, newer), teams, wiki)
    assert (len(again.unchanged), wiki.requests) == (2, [])  # cached: no request at all
    moved = await wiki_sync(cup(older, season_of("1960-61", (MAIN, 101))), teams, wiki)
    assert [s.label for _, s in moved.synced] == ["1960-61"] and [s.label for _, s in moved.unchanged] == ["1959-60"]
    async with get_sessionmaker()() as session:
        assert await session.scalar(select(func.count()).select_from(Match).where(Match.home_score == 2, Match.away_score == 0)) == 1


async def test_pins_tool_lists_box_changes(tmp_path: Path) -> None:
    wiki = fake()
    wiki.pages[(MAIN, 101)] = MAIN_HTML.replace("2–1", "2–0")
    store = RevisionStore(tmp_path, wiki)
    old = rows(await read_season(season((MAIN, 100)), store, {}))
    new = rows(await read_season(season((MAIN, 101)), store, {}))
    assert box_diff(old, new) == [
        "- First round | 1960-09-14 | Alpha F.C. | Beta F.C. | 2–1 REGULAR",
        "+ First round | 1960-09-14 | Alpha F.C. | Beta F.C. | 2–0 REGULAR",
    ]
    assert pins_yaml([WikipediaPin(title=MAIN, revision=100)]) == 'wikipedia_source:\n  - {title: "1960–61 European Cup", revision: 100}'
