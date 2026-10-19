"""Events ingestion against a real database (match-events spec; design D2, D5, D6)."""

import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from football_api.api.app import create_app
from football_api.domain.enums import CardKind, Coverage, LineupRole, Side, Stage
from football_api.infra.db import get_sessionmaker
from football_api.infra.models import Card, Competition, ExternalRef, LineupEntry, Match, Season, Substitution, Team
from football_api.ingestion.seeds import CompetitionSeed, TeamSeed, load_competitions
from football_api.sync import run_sync

pytestmark = pytest.mark.db

EVENTS_SEEDS = Path(__file__).parent / "fixtures" / "seeds" / "events-competitions.yaml"


@pytest.fixture(scope="session")
def events_competitions() -> list[CompetitionSeed]:
    return load_competitions(EVENTS_SEEDS)


async def sync(competitions: list[CompetitionSeed], teams: list[TeamSeed]) -> None:
    report = await run_sync(competitions=competitions, teams=teams, refresh_sources=False)
    assert not report.failed, report.failed


async def failures(competitions: list[CompetitionSeed], teams: list[TeamSeed]) -> list[str]:
    report = await run_sync(competitions=competitions, teams=teams, refresh_sources=False)
    return [str(exc) for _, _, exc in report.failed]


async def match_of(home: str, away: str, stage: Stage | None = None) -> Match:
    async with get_sessionmaker()() as session:
        home_id = select(Team.id).where(Team.name == home).scalar_subquery()
        away_id = select(Team.id).where(Team.name == away).scalar_subquery()
        query = select(Match).where(Match.home_team_id == home_id, Match.away_team_id == away_id)
        match = await session.scalar(query.where(Match.stage == stage) if stage else query)
        assert match is not None
        return match


async def rows[R: (LineupEntry, Substitution, Card)](model: type[R], match_id: uuid.UUID, side: Side | None = None) -> list[R]:
    async with get_sessionmaker()() as session:
        query = select(model).where(model.match_id == match_id)
        if side:
            query = query.where(model.side == side)
        return list(await session.scalars(query.order_by(model.side, model.ordinal)))


async def coverage_of(competition: str, label: str) -> tuple[Coverage, Coverage, Coverage]:
    async with get_sessionmaker()() as session:
        season = await session.scalar(
            select(Season).join(Competition).where(Competition.name == competition, Season.label == label)
        )
        assert season is not None
        return season.lineups_coverage, season.substitutions_coverage, season.cards_coverage


# --- 3.2 linking events-file matches to synced matches ----------------------------------


async def test_league_season_read_from_its_json_mirror_gets_events(
    fresh_db: Path, events_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    await sync(events_competitions, fixture_teams)
    match = await match_of("Burnley", "Liverpool")
    async with get_sessionmaker()() as session:
        refs = list(
            await session.scalars(select(ExternalRef.source_id).where(ExternalRef.entity_id == match.id))
        )
    assert refs and all(ref.startswith("football.json/2025-26/en.1.json#") for ref in refs)
    assert (match.referee_name, match.attendance) == ("Michael Oliver", 21678)
    burnley_cards = await rows(Card, match.id, Side.HOME)
    assert [(c.player_name, c.minute, c.kind) for c in burnley_cards] == [
        ("Lesley Ugochukwu", 16, CardKind.YELLOW),
        ("Lesley Ugochukwu", 84, CardKind.SECOND_YELLOW),
    ]


async def test_events_match_that_links_to_no_synced_match_fails(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    path = fresh_db / "worldcup/more/2022_full.txt"
    path.write_text(path.read_text(encoding="utf-8").replace("Sun Nov 20 19:00", "Sun Nov 27 19:00"), encoding="utf-8")
    assert await failures(fixture_competitions, fixture_teams) == [
        "worldcup/more/2022_full.txt:20: Qatar v Ecuador on 2022-11-27 links to no synced match"
    ]


async def test_events_match_that_links_to_two_synced_matches_fails(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    path = fresh_db / "worldcup/more/2022.txt"
    text = path.read_text(encoding="utf-8")
    pairing = "Sun Nov 20\n  19:00 UTC+3   Qatar  0-2  Ecuador   @ Al Bayt Stadium, Al Khor\n"
    assert pairing in text
    path.write_text(text.replace("▪ Final", f"▪ Final\n{pairing}", 1), encoding="utf-8")
    assert await failures(fixture_competitions, fixture_teams) == [
        "worldcup/more/2022_full.txt:20: Qatar v Ecuador on 2022-11-20 links to 2 synced matches"
    ]


# --- 3.3 player resolution -------------------------------------------------------------


async def test_event_names_resolve_against_the_squad(synced_db: str) -> None:
    final = await match_of("Argentina", "France", Stage.FINAL)
    argentina = await rows(LineupEntry, final.id, Side.HOME)
    messi = next(e for e in argentina if e.player_name == "Lionel Messi")
    assert messi.player_id is not None and messi.is_captain and messi.role is LineupRole.STARTER
    assert all(e.player_id is not None for e in argentina)


async def test_season_without_squads_keeps_names(
    fresh_db: Path, events_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    await sync(events_competitions, fixture_teams)
    match = await match_of("Liverpool", "AFC Bournemouth")
    entries = await rows(LineupEntry, match.id)
    subs = await rows(Substitution, match.id)
    cards = await rows(Card, match.id)
    assert len(entries) == 2 * 11 + 9 and len(subs) == 9 and len(cards) == 3
    assert all(e.player_id is None for e in entries)
    assert all(s.player_off_id is None and s.player_on_id is None for s in subs)
    assert "Virgil Van Dijk" in [e.player_name for e in entries]


# --- 3.4 upserts, surplus and removed matches ---------------------------------------------


async def test_source_drops_a_card(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    await sync(fixture_competitions, fixture_teams)
    match = await match_of("Qatar", "Ecuador")
    before = await rows(Card, match.id, Side.HOME)
    assert [c.player_name for c in before] == ["Saad Alsheeb", "Karim Boudiaf", "Akram Afif", "Almoez Ali"]

    path = fresh_db / "worldcup/more/2022_full.txt"
    path.write_text(path.read_text(encoding="utf-8").replace("ALMOEZ ALI [Y 22']", "ALMOEZ ALI"), encoding="utf-8")
    await sync(fixture_competitions, fixture_teams)

    after = await rows(Card, match.id, Side.HOME)
    assert [c.id for c in after] == [c.id for c in before[:3]]


async def test_removed_match_takes_its_events(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    await sync(fixture_competitions, fixture_teams)
    match = await match_of("Qatar", "Ecuador")
    assert await rows(LineupEntry, match.id)

    plain = fresh_db / "worldcup/more/2022.txt"
    plain.write_text(
        plain.read_text(encoding="utf-8").replace(
            "Sun Nov 20\n  19:00 UTC+3   Qatar  0-2  Ecuador   @ Al Bayt Stadium, Al Khor\n"
            "                  (Enner VALENCIA 16'(p), 31')\n",
            "",
        ),
        encoding="utf-8",
    )
    full = fresh_db / "worldcup/more/2022_full.txt"
    text = full.read_text(encoding="utf-8")
    start = text.index("Sun Nov 20 19:00")
    full.write_text(text[:start] + text[text.index("Mon Nov 21 19:00") :], encoding="utf-8")
    await sync(fixture_competitions, fixture_teams)

    async with get_sessionmaker()() as session:
        assert await session.get(Match, match.id) is None
        for model in (LineupEntry, Substitution, Card):
            assert await session.scalar(select(func.count()).select_from(model).where(model.match_id == match.id)) == 0


async def test_referee_and_attendance(synced_db: str) -> None:
    final = await match_of("Chelsea", "Paris Saint-Germain")
    assert (final.referee_name, final.attendance) == ("Alireza Faghani", 81118)


# --- 3.5 coverage ---------------------------------------------------------------------


async def test_coverage_from_the_events_file(
    fresh_db: Path,
    fixture_competitions: list[CompetitionSeed],
    events_competitions: list[CompetitionSeed],
    fixture_teams: list[TeamSeed],
) -> None:
    await sync(fixture_competitions, fixture_teams)
    await sync(events_competitions, fixture_teams)
    full, none = Coverage.FULL, Coverage.NONE
    assert await coverage_of("FIFA World Cup", "2022") == (full, full, full)
    assert await coverage_of("FIFA Club World Cup", "2018") == (full, none, none)
    assert await coverage_of("Premier League", "2025-26") == (full, full, full)
    assert await coverage_of("Premier League", "2024-25") == (none, none, none)
    assert await coverage_of("CONMEBOL Copa Libertadores", "2025") == (none, none, none)

    al_ain = await match_of("Al Ain", "Team Wellington")
    assert {e.line_index for e in await rows(LineupEntry, al_ain.id)} == {1}


async def test_api_formation_is_null_without_line_groups(
    fresh_db: Path, events_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    await sync(events_competitions, fixture_teams)
    match = await match_of("Al Ain", "Team Wellington")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test") as client:
        resp = await client.get(f"/v1/matches/{match.id}?expand=lineups,substitutions,cards")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["lineups"]["home"]["formation"] is body["lineups"]["away"]["formation"] is None
    assert len(body["lineups"]["home"]["entries"]) == 11
    assert body["substitutions"] == body["cards"] == []
    assert body["coverage"] == {"scorers": "full", "lineups": "full", "substitutions": "none", "cards": "none"}
