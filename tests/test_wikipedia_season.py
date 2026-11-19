"""Wikipedia as a season source: headings, pinned revisions and their cache, boxes to matches
(ingestion spec: Wikipedia season source, Pinned revisions are cached, Stage from section headings,
Walkovers, Results grid cells, Grid sections, Awarded matches in grids; design D2–D5, and
la-liga-history-from-wikipedia D4, D5)."""

from collections.abc import Iterable
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from football_api.domain.enums import DecidedBy, EntityType, MatchStatus, Played, Stage, TeamKind
from football_api.infra.db import get_sessionmaker
from football_api.infra.models import ExternalRef, Match, Season, Team, TeamSeason
from football_api.ingestion.openfootball.text_parser import normalize_stage
from football_api.ingestion.seeds import AwardedSeeds, CompetitionSeed, SeasonSource, TeamSeed, WikipediaPin
from football_api.ingestion.wikipedia import (
    WikipediaUnavailable,
    parse_match_boxes,
    parse_results_grid,
    parse_season_grids,
    parse_subarticle_titles,
)
from football_api.ingestion.wikipedia_season import (
    RevisionStore,
    WikipediaSourceError,
    grid_label,
    read_grid_season,
    read_season,
    round_label,
    seeded_qids,
    source_of,
)
from football_api.season_tables import season_tables
from football_api.standings import group_of, phase_of
from football_api.sync import SyncReport, run_sync
from football_api.wikipedia_pins import box_diff, pins_yaml, rows
from football_api.wikipedia_pins import read as pins_read


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
        # Wrappers name no stage (cup-winners-cup-and-uefa-cup-from-wikipedia D2).
        ("", ("Final phase", "Third round"), "Third round", Stage.ROUND, 3),
        ("", ("Tournament phase", "Semi-finals"), "Semi-finals", Stage.SF, None),
        ("", ("Qualifying phase", "Preliminary round"), "Preliminary round", Stage.PRELIMINARY, None),
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


# --- league seasons from results grids (la-liga-history-from-wikipedia) ------------------------
LIGA = "1979–80 La Liga"
GRID_QIDS = {"Alpha CF": "Q1", "Beta CF": "Q2", "Gamma CF": "Q3", "Old Gamma": "Q3", "Delta CF": "Q4"}


def grid(rows: list[str], cells: list[list[str]], columns: list[str] | None = None) -> str:
    """A results grid: `rows` link the home clubs, `columns` (default: the same) the away clubs."""
    head = "<tr><th>Home \\ Away</th>" + "".join(f"<th>{club(c)}</th>" for c in columns or rows) + "</tr>"
    body = "".join(
        f"<tr><th>{club(r)}</th>" + "".join(f"<td>{'—' if i == j else c}</td>" for j, c in enumerate(row)) + "</tr>"
        for i, (r, row) in enumerate(zip(rows, cells, strict=True))
    )
    return f'<table class="wikitable">{head}{body}</table>'


THREE = ["Alpha CF", "Beta CF", "Gamma CF"]
SCORES = [["", "2–1", "1–1"], ["0–0", "", "3–2"], ["1–0", "", ""]]  # Gamma v Beta has no result
LIGA_HTML = section("Results", grid(THREE, SCORES)) + section("Relegation play-off", "<p>no grid here</p>")


def grid_page(*sections: str) -> str:
    return f"<html><head><title>{LIGA}</title></head><body>{''.join(sections)}</body></html>"


def grid_season(revision: int = 100, grids: list[str] | None = None) -> SeasonSource:
    data: dict[str, object] = {"label": "1979-80", "start_year": 1979, "wikipedia_source": [{"title": LIGA, "revision": revision}]}
    if grids:
        data["wikipedia_grids"] = grids
    return SeasonSource.model_validate(data)


def grid_fake(html: str, revision: int = 100) -> FakeWikipedia:
    return FakeWikipedia({(LIGA, revision): html}, GRID_QIDS)


async def read_grid(tmp_path: Path, html: str, grids: list[str] | None = None) -> list[tuple[str, str, str, str]]:
    got = await read_grid_season(grid_season(grids=grids), RevisionStore(tmp_path, grid_fake(html)), {})
    return [
        (m.round_label, m.home, m.away, f"{m.score.home}–{m.score.away}" if m.score else m.status.value) for m in got.matches
    ]


def test_grids_carry_headings_and_positions() -> None:
    [g] = parse_season_grids(grid_page(LIGA_HTML))
    assert g.heading == ("Results",) and g.rows == THREE == g.columns
    assert [(c.row, c.column, c.score) for c in g.cells][:2] == [(0, 1, (2, 1)), (0, 2, (1, 1))]
    assert len(g.cells) == 6  # the diagonal is skipped
    # Verification's reader is unchanged: the first grid, by title.
    reference = parse_results_grid(grid_page(LIGA_HTML))
    assert reference is not None and len(reference.cells) == 6


@pytest.mark.parametrize(
    ("heading", "label"),
    [
        (("Results",), "League"),
        (("Regular season", "Results"), "League"),
        (("Championship group", "Results"), "Championship group"),
        (("Relegation play-off", "Results"), None),
        (("Trivia",), None),
    ],
)
def test_grid_label(heading: tuple[str, ...], label: str | None) -> None:
    assert grid_label(heading) == label


def test_named_groups_map_to_their_group() -> None:
    assert normalize_stage("Championship group")[0] is Stage.GROUP and group_of("Championship group") == "Championship"
    assert normalize_stage("League") == (Stage.LEAGUE, None)
    assert group_of("First group stage") is None and group_of("Second group stage / Group A") == "A"


async def test_league_season_from_its_grid(tmp_path: Path) -> None:
    assert await read_grid(tmp_path, grid_page(LIGA_HTML)) == [
        ("League", "Q1", "Q2", "2–1"),
        ("League", "Q1", "Q3", "1–1"),
        ("League", "Q2", "Q1", "0–0"),
        ("League", "Q2", "Q3", "3–2"),
        ("League", "Q3", "Q1", "1–0"),
        ("League", "Q3", "Q2", "CANCELLED"),
    ]


async def test_row_and_column_named_differently_pair_by_position(tmp_path: Path) -> None:
    html = grid_page(section("Results", grid(["Alpha CF", "Beta CF", "Old Gamma"], SCORES, columns=THREE)))
    matches = await read_grid(tmp_path, html)
    assert len(matches) == 6 and all(home != away for _, home, away, _ in matches)


async def test_row_and_column_that_dont_match_fail(tmp_path: Path) -> None:
    html = grid_page(section("Results", grid(["Alpha CF", "Beta CF", "Delta CF"], SCORES, columns=THREE)))
    with pytest.raises(WikipediaSourceError, match=r"revision 100\): row 3 is 'Delta CF' \(Q4\) but column 3 is 'Gamma CF' \(Q3\)"):
        await read_grid(tmp_path, html)


async def test_cell_that_is_not_a_score_fails(tmp_path: Path) -> None:
    html = grid_page(section("Results", grid(THREE, [["", "2–1", "1–1"], ["0–0", "", "3–2"], ["1–0", "a", ""]])))
    with pytest.raises(WikipediaSourceError, match="Gamma CF v Beta CF reads 'a'"):
        await read_grid(tmp_path, html)


async def test_second_phase_in_groups(tmp_path: Path) -> None:
    two = [["", "1–0"], ["2–2", ""]]
    html = grid_page(
        section("Regular season", section("Results", grid(THREE, SCORES), level=3)),
        section("Championship group", section("Results", grid(THREE[:2], two), level=3)),
        section("Relegation group", section("Results", grid(THREE[1:], two), level=3)),
    )
    matches = await read_grid(tmp_path, html, ["Regular season", "Championship group", "Relegation group"])
    assert [m[0] for m in matches] == ["League"] * 6 + ["Championship group"] * 2 + ["Relegation group"] * 2


async def test_only_the_seeded_sections_are_read(tmp_path: Path) -> None:
    # As in 1950-51: the relegation group's own `Results` subsection isn't the league's `Results`.
    relegation = section("Results", grid(["Beta CF", "Delta CF"], [["", "1–0"], ["2–2", ""]]), level=3)
    html = grid_page(LIGA_HTML, section("Relegation group", relegation))
    assert len(await read_grid(tmp_path, html, ["Results"])) == 6


async def test_several_grids_and_no_sections_fail(tmp_path: Path) -> None:
    html = grid_page(LIGA_HTML, section("Relegation group", grid(["Beta CF", "Delta CF"], [["", "1–0"], ["2–2", ""]])))
    with pytest.raises(WikipediaSourceError, match=r"2 results grids .*revision 100\): Results; .*Relegation group"):
        await read_grid(tmp_path, html)
    with pytest.raises(WikipediaSourceError, match="no results grid under the section 'Second phase'"):
        await read_grid(tmp_path, html, ["Results", "Second phase"])


def test_grids_need_a_wikipedia_league_season() -> None:
    with pytest.raises(ValueError, match="needs `wikipedia_source`"):
        SeasonSource.model_validate({"label": "2024-25", "start_year": 2024, "file": "x.txt", "tz": "UTC", "wikipedia_grids": ["Results"]})
    cup = {"name": "Cup", "team_kind": "CLUB", "scope": "DOMESTIC", "format": "CUP", "wikidata": "Q9"}
    with pytest.raises(ValueError, match="only for leagues"):
        CompetitionSeed.model_validate({**cup, "seasons": [grid_season(grids=["Results"]).model_dump(by_alias=True, exclude_unset=True)]})


async def test_pins_tool_lists_cell_changes(tmp_path: Path) -> None:
    wiki = FakeWikipedia({(LIGA, 100): grid_page(LIGA_HTML), (LIGA, 101): grid_page(LIGA_HTML.replace("3–2", "3–3"))}, GRID_QIDS)
    store = RevisionStore(tmp_path, wiki)
    old = rows(await read_grid_season(grid_season(100), store, {}))
    new = rows(await read_grid_season(grid_season(101), store, {}))
    assert box_diff(old, new) == [
        "- League | no date | Beta CF | Gamma CF | 3–2 REGULAR",
        "+ League | no date | Beta CF | Gamma CF | 3–3 REGULAR",
    ]


# --- sync ---------------------------------------------------------------------------------

LEAGUE = {"name": "La Liga", "country": "ES", "team_kind": "CLUB", "scope": "DOMESTIC", "format": "LEAGUE", "wikidata": "Q324867"}
GRID_CLUBS = [TeamSeed(name=n, kind=TeamKind.CLUB, country=None, wikidata=q) for n, q in GRID_QIDS.items() if n != "Old Gamma"]


def league(src: SeasonSource) -> list[CompetitionSeed]:
    return [CompetitionSeed.model_validate({**LEAGUE, "seasons": [src.model_dump(by_alias=True, exclude_unset=True)]})]


async def grid_sync(teams: list[TeamSeed], awarded: AwardedSeeds | None = None, html: str = grid_page(LIGA_HTML)) -> SyncReport:
    # Never the shipped awarded.yaml, whose real La Liga 1979-80 entry this fake season would trip.
    return await run_sync(
        competitions=league(grid_season()), teams=teams, awarded=awarded or AwardedSeeds(), refresh_sources=False, wikipedia=grid_fake(html)
    )


def awarded_entry(home: str, away: str) -> AwardedSeeds:
    return AwardedSeeds.model_validate(
        {"matches": [{"competition": "Q324867", "season": "1979-80", "home": home, "away": away, "played": "NONE", "reason": "r", "source": "s"}]}
    )


@pytest.mark.db
async def test_grid_season_syncs_without_dates(fresh_db: Path, fixture_teams: list[TeamSeed]) -> None:
    report = await grid_sync(fixture_teams + GRID_CLUBS)
    assert not report.failed, report.failed
    async with get_sessionmaker()() as session:
        row = (await session.scalars(select(Season).where(Season.label == "1979-80"))).one()
        assert row.source["license"] == "CC-BY-SA-4.0" and row.starts_on is None
        matches = (await session.scalars(select(Match).where(Match.season_id == row.id))).all()
    assert len(matches) == 6 and all(m.kickoff_utc is None and m.stage is Stage.LEAGUE for m in matches)
    assert sorted(m.status for m in matches) == [MatchStatus.CANCELLED] + [MatchStatus.COMPLETED] * 5


@pytest.mark.db
async def test_awarded_match_from_the_seed(fresh_db: Path, fixture_teams: list[TeamSeed]) -> None:
    report = await grid_sync(fixture_teams + GRID_CLUBS, awarded_entry("Q3", "Q1"))
    assert not report.failed, report.failed
    async with get_sessionmaker()() as session:
        flagged = (await session.scalars(select(Match).where(Match.awarded))).all()
    assert [(m.home_score, m.away_score, m.played) for m in flagged] == [(1, 0, Played.NONE)]


@pytest.mark.db
async def test_awarded_entry_without_its_match_fails(fresh_db: Path, fixture_teams: list[TeamSeed]) -> None:
    report = await grid_sync(fixture_teams + GRID_CLUBS + [TeamSeed(name="Epsilon", kind=TeamKind.CLUB, country=None, wikidata="Q5")], awarded_entry("Q5", "Q1"))
    [(_, _, exc)] = report.failed
    assert "awarded.yaml lists Q5 v Q1, not in the season" in str(exc)


# --- skipped sections and seeded QIDs (cup-winners-cup-and-uefa-cup-from-wikipedia D3, D4) --------


def with_options(src: SeasonSource, **options: object) -> SeasonSource:
    return SeasonSource.model_validate({**src.model_dump(by_alias=True, exclude_unset=True), **options})


async def test_skipped_sections_are_not_read(tmp_path: Path) -> None:
    src = with_options(season((MAIN, 100)), wikipedia_skip=["Quarter-finals"])
    read = await read_season(src, RevisionStore(tmp_path, fake()), {})
    assert {m.round_label for m in read.matches} == {"First round", "Final"}


async def test_skipped_section_that_isnt_there_fails(tmp_path: Path) -> None:
    src = with_options(season((MAIN, 100)), wikipedia_skip=["Quarter-finals", "Preliminary round"])
    with pytest.raises(WikipediaSourceError, match="no boxes under the skipped section\\(s\\) 'Preliminary round'"):
        await read_season(src, RevisionStore(tmp_path, fake()), {})


async def test_seeded_qid_for_a_club_without_an_article(tmp_path: Path) -> None:
    wiki = FakeWikipedia({(MAIN, 100): MAIN_HTML}, {t: q for t, q in QIDS.items() if t != "Delta F.C."})
    with pytest.raises(WikipediaSourceError, match="'Delta F.C.' has no Wikidata QID"):
        await read_season(season((MAIN, 100)), RevisionStore(tmp_path / "a", wiki), {})
    read = await read_season(with_options(season((MAIN, 100)), wikipedia_qids={"Delta F.C.": "Q4"}), RevisionStore(tmp_path / "b", wiki), {})
    assert "Q4" in {m.away for m in read.matches} | {m.home for m in read.matches}


async def test_seeded_qid_no_box_links_fails(tmp_path: Path) -> None:
    src = with_options(season((MAIN, 100)), wikipedia_qids={"Nobody F.C.": "Q9"})
    with pytest.raises(WikipediaSourceError, match="names 'Nobody F.C.', which no box links"):
        await read_season(src, RevisionStore(tmp_path, fake()), {})


@pytest.mark.parametrize("option", [{"wikipedia_skip": ["Qualifying round"]}, {"wikipedia_qids": {"X": "Q1"}}])
def test_wikipedia_options_need_a_wikipedia_season(option: dict[str, object]) -> None:
    [name] = option
    with pytest.raises(ValueError, match=f"`{name}` needs `wikipedia_source`"):
        SeasonSource.model_validate({"label": "2024-25", "start_year": 2024, "file": "x.txt", "tz": "UTC", **option})


async def test_pins_tool_reads_seeded_options(tmp_path: Path) -> None:
    wiki = fake()
    wiki.pages[(MAIN, 101)] = MAIN_HTML.replace("2–1", "2–0")
    store = RevisionStore(tmp_path, wiki)
    old = with_options(season((MAIN, 100)), wikipedia_skip=["Quarter-finals"])
    new = old.model_copy(update={"wikipedia_source": [WikipediaPin(title=MAIN, revision=101)]})
    diff = box_diff(rows(await pins_read(old, store, grids=False)), rows(await pins_read(new, store, grids=False)))
    assert diff == [
        "- First round | 1960-09-14 | Alpha F.C. | Beta F.C. | 2–1 REGULAR",
        "+ First round | 1960-09-14 | Alpha F.C. | Beta F.C. | 2–0 REGULAR",
    ]


# --- renamed headings and abandoned matches (euro-and-copa-america-from-wikipedia D3, D4) ----------

ROBIN = "1916 South American Championship"
ROBIN_HTML = (
    f"<html><head><title>{ROBIN}</title></head><body>"
    + section(
        "Results",
        box("1916-07-02", "Alpha F.C.", "Beta F.C.", "4–0"),
        box("1916-07-06", "Gamma F.C.", "Delta F.C.", "6–1"),
        box("1916-07-08", "Beta F.C.", "Delta F.C.", "1–1"),
        box("1916-07-10", "Gamma F.C.", "Beta F.C.", "1–1"),
        box("1916-07-12", "Alpha F.C.", "Delta F.C.", "2–1"),
        box("1916-07-16", "Gamma F.C.", "Alpha F.C.", "0–0"),
        box("1916-07-17", "Gamma F.C.", "Alpha F.C.", "0–0"),
        section("Play-off", box("1916-07-20", "Alpha F.C.", "Beta F.C.", "1–0"), level=3),
    )
    + "</body></html>"
)
ABANDONED = {"date": "1916-07-16", "home": "Q3", "away": "Q1", "reason": "Abandoned at 0-0 after crowd trouble; replayed"}


def robin() -> FakeWikipedia:
    return FakeWikipedia({(ROBIN, 300): ROBIN_HTML}, QIDS)


def test_round_robin_heading_renamed_to_a_group_stage() -> None:
    assert round_label("", ("Group stage", "Play-off")) == "Group stage"
    assert normalize_stage("Group stage") == (Stage.GROUP, None) and group_of("Group stage") is None
    assert normalize_stage("Second group stage") == (Stage.GROUP, None) and phase_of("Second group stage") == 2


async def test_renamed_heading_gives_the_round_label(tmp_path: Path) -> None:
    src = with_options(season((ROBIN, 300)), wikipedia_rounds={"results": "Group stage"})
    read = await read_season(src, RevisionStore(tmp_path, robin()), {})
    assert len(read.matches) == 8 and {m.round_label for m in read.matches} == {"Group stage"}


async def test_unrenamed_round_robin_names_no_stage(tmp_path: Path) -> None:
    with pytest.raises(WikipediaSourceError, match="heading 'Results' names no stage"):
        await read_season(season((ROBIN, 300)), RevisionStore(tmp_path, robin()), {})


async def test_final_round_renamed_to_a_second_group_stage(tmp_path: Path) -> None:
    html = ROBIN_HTML.replace("<h2>Results</h2>", "<h2>Final round</h2>")
    wiki = FakeWikipedia({(ROBIN, 300): html}, QIDS)
    plain = await read_season(season((ROBIN, 300)), RevisionStore(tmp_path / "a", wiki), {})
    assert {normalize_stage(m.round_label)[0] for m in plain.matches} == {Stage.FINAL}
    src = with_options(season((ROBIN, 300)), wikipedia_rounds={"Final round": "Second group stage"})
    read = await read_season(src, RevisionStore(tmp_path / "b", wiki), {})
    assert {m.round_label for m in read.matches} == {"Second group stage"}


async def test_renamed_heading_that_isnt_there_fails(tmp_path: Path) -> None:
    src = with_options(season((MAIN, 100)), wikipedia_rounds={"Results": "Group stage"})
    with pytest.raises(WikipediaSourceError, match="no boxes under the renamed section\\(s\\) 'Results'"):
        await read_season(src, RevisionStore(tmp_path, fake()), {})


async def test_abandoned_match_is_cancelled_and_its_replay_kept(tmp_path: Path) -> None:
    src = with_options(season((ROBIN, 300)), wikipedia_rounds={"Results": "Group stage"}, wikipedia_abandoned=[ABANDONED])
    read = await read_season(src, RevisionStore(tmp_path, robin()), {})
    gamma_alpha = [m for m in read.matches if (m.home, m.away) == ("Q3", "Q1")]
    assert [(m.day, m.status, m.score) for m in gamma_alpha] == [
        (date(1916, 7, 16), MatchStatus.CANCELLED, None),
        (date(1916, 7, 17), MatchStatus.COMPLETED, gamma_alpha[1].score),
    ]
    assert gamma_alpha[1].score is not None and (gamma_alpha[1].score.home, gamma_alpha[1].score.away) == (0, 0)


async def test_abandoned_match_no_box_holds_fails(tmp_path: Path) -> None:
    stale = {**ABANDONED, "date": "1916-07-15"}
    src = with_options(season((ROBIN, 300)), wikipedia_rounds={"Results": "Group stage"}, wikipedia_abandoned=[stale])
    with pytest.raises(WikipediaSourceError, match="lists Q3 v Q1 on 1916-07-15, which no box holds"):
        await read_season(src, RevisionStore(tmp_path, robin()), {})


@pytest.mark.parametrize("option", [{"wikipedia_rounds": {"Results": "Group stage"}}, {"wikipedia_abandoned": [ABANDONED]}])
def test_new_options_need_a_wikipedia_season(option: dict[str, object]) -> None:
    [name] = option
    with pytest.raises(ValueError, match=f"`{name}` needs `wikipedia_source`"):
        SeasonSource.model_validate({"label": "1916", "start_year": 1916, "file": "x.txt", "tz": "UTC", **option})


async def test_pins_tool_reads_renames_and_abandoned_matches(tmp_path: Path) -> None:
    wiki = robin()
    wiki.pages[(ROBIN, 301)] = ROBIN_HTML.replace("4–0", "3–0")
    store = RevisionStore(tmp_path, wiki)
    old = with_options(season((ROBIN, 300)), wikipedia_rounds={"Results": "Group stage"}, wikipedia_abandoned=[ABANDONED])
    new = old.model_copy(update={"wikipedia_source": [WikipediaPin(title=ROBIN, revision=301)]})
    assert "Group stage | 1916-07-16 | Gamma F.C. | Alpha F.C. | no result" in {" | ".join(r) for r in rows(await pins_read(old, store, grids=False))}
    diff = box_diff(rows(await pins_read(old, store, grids=False)), rows(await pins_read(new, store, grids=False)))
    assert diff == [
        "- Group stage | 1916-07-02 | Alpha F.C. | Beta F.C. | 4–0 REGULAR",
        "+ Group stage | 1916-07-02 | Alpha F.C. | Beta F.C. | 3–0 REGULAR",
    ]


@pytest.mark.db
async def test_round_robin_table_counts_the_replay_not_the_abandoned_match(fresh_db: Path, fixture_teams: list[TeamSeed]) -> None:
    src = with_options(season((ROBIN, 300)), wikipedia_rounds={"Results": "Group stage"}, wikipedia_abandoned=[ABANDONED])
    report = await wiki_sync(cup(src), fixture_teams + CLUBS, robin())
    assert not report.failed, report.failed
    async with get_sessionmaker()() as session:
        row = (await session.scalars(select(Season))).one()
        matches = (await session.scalars(select(Match).where(Match.season_id == row.id))).all()
        assert sorted(m.status for m in matches) == [MatchStatus.CANCELLED] + [MatchStatus.COMPLETED] * 7
        assert {m.stage for m in matches} == {Stage.GROUP}
        gamma_alpha = sorted((m.occurrence, m.status) for m in matches if m.status is MatchStatus.CANCELLED or m.home_score == m.away_score == 0)
        assert gamma_alpha == [(1, MatchStatus.CANCELLED), (2, MatchStatus.COMPLETED)]
        [table] = await season_tables(session, row)
    # The play-off repeats Alpha v Beta, so it stays out; the abandoned match is cancelled.
    assert sorted(r.played for r in table.rows) == [3, 3, 3, 3]
