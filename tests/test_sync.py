"""Ingestion against a real database: idempotency and reconciliation scenarios (ingestion spec)."""

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from football_api.domain.enums import Coverage, DecidedBy, MatchStatus, Stage, VerificationReference, VerificationStatus
from football_api.infra.db import get_sessionmaker
from football_api.infra.models import Competition, ExternalRef, Goal, Match, MatchVerification, Player, Season, Team, TeamSeason
from football_api.ingestion.openfootball.squads import parse_more_squads, parse_per_team_squad
from football_api.ingestion.seeds import CompetitionSeed, TeamSeed
from football_api.sync import UnknownTeamError, run_sync

pytestmark = pytest.mark.db

FIXTURE_SOURCES = Path(__file__).parent / "fixtures" / "sources"

MANAGED_TABLES = [
    "competition", "season", "team", "team_season", "venue", "player",
    "player_team_season", "match", "goal", "external_ref",
]


async def snapshot() -> dict[str, list[str]]:
    async with get_sessionmaker()() as session:
        out: dict[str, list[str]] = {}
        for table in MANAGED_TABLES:
            rows = await session.execute(text(f"SELECT t::text FROM {table} t ORDER BY 1"))
            out[table] = [r[0] for r in rows]
        return out


async def sync(competitions: list[CompetitionSeed], teams: list[TeamSeed]) -> None:
    report = await run_sync(competitions=competitions, teams=teams, refresh_sources=False)
    assert not report.failed, report.failed


async def match_by(home: str, away: str, stage: Stage) -> Match:
    """Find a match by its teams' names, as a client listing teams would."""
    async with get_sessionmaker()() as session:
        home_id = select(Team.id).where(Team.name == home).scalar_subquery()
        away_id = select(Team.id).where(Team.name == away).scalar_subquery()
        match = await session.scalar(
            select(Match).where(Match.home_team_id == home_id, Match.away_team_id == away_id, Match.stage == stage)
        )
        assert match is not None
        return match


async def goals_of(match: Match) -> list[Goal]:
    async with get_sessionmaker()() as session:
        return list(await session.scalars(select(Goal).where(Goal.match_id == match.id).order_by(Goal.ordinal)))


def published_squad_size(competitions: list[CompetitionSeed], sources: Path) -> int:
    total = 0
    for comp in competitions:
        for season in comp.seasons:
            squads = season.squads
            if squads is None:
                continue
            for pattern in squads.files:
                for path in sources.glob(pattern):
                    text = path.read_text(encoding="utf-8")
                    total += len(parse_more_squads(text) if squads.style == "more" else parse_per_team_squad(text))
    return total


async def test_first_sync_populates_everything(synced_db: str, fixture_competitions: list[CompetitionSeed]) -> None:
    async with get_sessionmaker()() as session:
        counts = {
            model.__tablename__: await session.scalar(select(func.count()).select_from(model))
            for model in (Competition, Season, Match, Goal, Player)
        }
    players = published_squad_size(fixture_competitions, FIXTURE_SOURCES)
    assert counts == {"competition": 8, "season": 8, "match": 84, "goal": 37, "player": players}


async def test_reconciled_values(synced_db: str) -> None:
    final = await match_by("Argentina", "France", Stage.FINAL)
    assert (final.home_score, final.away_score, final.decided_by, final.home_pens, final.away_pens) == (
        3, 3, DecidedBy.PENALTIES, 4, 2,
    )
    assert final.kickoff_utc == datetime(2022, 12, 18, 15, 0, tzinfo=UTC)  # 18:00 UTC+3
    goals = await goals_of(final)
    assert [g.minute for g in goals] == [23, 108, 36, 80, 81, 118]
    assert all(g.scorer_player_id is not None for g in goals)

    pl = await match_by("Manchester United", "Fulham", Stage.LEAGUE)
    assert pl.kickoff_utc == datetime(2024, 8, 16, 19, 0, tzinfo=UTC)  # 20:00 Europe/London (BST)

    cwc = await match_by("Al Ahly", "Inter Miami", Stage.GROUP)
    assert cwc.kickoff_utc == datetime(2025, 6, 15, 0, 0, tzinfo=UTC)  # Sat 20:00 UTC-4

    postponed = await match_by("CSD Colo-Colo", "Fortaleza", Stage.GROUP)
    assert postponed.status is MatchStatus.POSTPONED and postponed.home_score is None

    async with get_sessionmaker()() as session:
        messi = await session.scalar(select(Player).where(Player.display_name == "Lionel Messi"))
        assert messi is not None and (messi.given_name, messi.family_name) == ("Lionel", "Messi")
        assert await session.scalar(select(func.count()).select_from(Player).where(Player.display_name.contains("MESSI"))) == 0
        coverage = dict(
            (await session.execute(select(Competition.name, Season.scorers_coverage).join(Season))).all()
        )
    assert coverage["FIFA World Cup"] is Coverage.FULL
    assert coverage["Premier League"] is Coverage.NONE


async def test_repeat_sync_is_byte_for_byte_identical(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    await sync(fixture_competitions, fixture_teams)
    first = await snapshot()
    await sync(fixture_competitions, fixture_teams)
    assert await snapshot() == first


async def test_goal_list_shrinks_after_source_correction(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    await sync(fixture_competitions, fixture_teams)
    final = await match_by("Argentina", "France", Stage.FINAL)
    before = await goals_of(final)
    assert len(before) == 6

    path = fresh_db / "worldcup/more/2022.txt"
    path.write_text(path.read_text(encoding="utf-8").replace(", 118'(p))", ")"), encoding="utf-8")
    await sync(fixture_competitions, fixture_teams)

    after = await goals_of(final)
    assert [g.ordinal for g in after] == [1, 2, 3, 4, 5]
    assert [g.id for g in after] == [g.id for g in before[:5]]


async def test_postponed_match_keeps_a_single_row(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    await sync(fixture_competitions, fixture_teams)
    original = await match_by("Manchester United", "Fulham", Stage.LEAGUE)

    path = fresh_db / "england/2024-25/1-premierleague.txt"
    path.write_text(path.read_text(encoding="utf-8").replace("    20:00  Manchester United FC", "    21:30  Manchester United FC"), encoding="utf-8")
    competitions = [
        c.model_copy(update={"seasons": [s.model_copy(update={"json_file": None}) for s in c.seasons]})
        for c in fixture_competitions
    ]
    await sync(competitions, fixture_teams)

    moved = await match_by("Manchester United", "Fulham", Stage.LEAGUE)
    assert moved.id == original.id
    assert moved.kickoff_utc == datetime(2024, 8, 16, 20, 30, tzinfo=UTC)
    assert moved.original_kickoff_utc == original.kickoff_utc

    # A second move keeps the first-observed original kickoff.
    path.write_text(path.read_text(encoding="utf-8").replace("    21:30  Manchester United FC", "    22:00  Manchester United FC"), encoding="utf-8")
    await sync(competitions, fixture_teams)
    again = await match_by("Manchester United", "Fulham", Stage.LEAGUE)
    assert again.original_kickoff_utc == original.kickoff_utc


async def test_unknown_team_fails_without_partial_writes(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    path = fresh_db / "deutschland/2024-25/1-bundesliga.txt"
    path.write_text(path.read_text(encoding="utf-8").replace("1. FC Union Berlin", "Union Berlin XI"), encoding="utf-8")
    bundesliga = [c for c in fixture_competitions if c.name == "Bundesliga"]

    report = await run_sync(competitions=bundesliga, teams=fixture_teams, refresh_sources=False)

    [(_, season, exc)] = report.failed
    assert season.label == "2024-25" and isinstance(exc, UnknownTeamError)
    assert re.search(r"deutschland/2024-25/1-bundesliga.txt:\d+: unknown team 'Union Berlin XI'", str(exc))
    async with get_sessionmaker()() as session:
        assert await session.scalar(select(func.count()).select_from(Season)) == 0
        assert await session.scalar(select(func.count()).select_from(Match)) == 0


async def test_renamed_team_keeps_its_row(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    """Teams are matched through their external refs, so editing a name in teams.yaml is safe."""
    await sync(fixture_competitions, fixture_teams)
    async with get_sessionmaker()() as session:
        before = await session.scalar(select(Team).where(Team.name == "Manchester United"))
    assert before is not None

    renamed = [t.model_copy(update={"name": "Man Utd"}) if t.name == "Manchester United" else t for t in fixture_teams]
    await sync(fixture_competitions, renamed)

    async with get_sessionmaker()() as session:
        after = await session.scalar(select(Team).where(Team.name == "Man Utd"))
        total = await session.scalar(select(func.count()).select_from(Team))
    assert after is not None and after.id == before.id
    assert total == len(fixture_teams)


async def test_renamed_competition_keeps_its_row(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    """Competitions are matched through their Wikidata QID."""
    await sync(fixture_competitions, fixture_teams)
    async with get_sessionmaker()() as session:
        before = await session.scalar(select(Competition.id).where(Competition.name == "FIFA World Cup"))

    renamed = [c.model_copy(update={"name": "World Cup"}) if c.name == "FIFA World Cup" else c for c in fixture_competitions]
    await sync(renamed, fixture_teams)

    async with get_sessionmaker()() as session:
        after = await session.scalar(select(Competition.id).where(Competition.name == "World Cup"))
        total = await session.scalar(select(func.count()).select_from(Competition))
    assert after == before
    assert total == len(fixture_competitions)


async def test_competition_with_two_seasons(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    """Each season in a seed becomes its own season row with its own matches (catalog spec)."""
    (fresh_db / "england/2023-24").mkdir(exist_ok=True)
    (fresh_db / "england/2023-24/1-premierleague.txt").write_text(
        (fresh_db / "england/2024-25/1-premierleague.txt").read_text(encoding="utf-8").replace("2024", "2023"),
        encoding="utf-8",
    )
    pl = next(c for c in fixture_competitions if c.name == "Premier League")
    current = pl.seasons[0]
    earlier = current.model_copy(
        update={"label": "2023-24", "start_year": 2023, "file": "england/2023-24/1-premierleague.txt", "json_file": None}
    )
    await sync([pl.model_copy(update={"seasons": [earlier, current]})], fixture_teams)

    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                select(Season.label, func.count(Match.id)).join(Match).group_by(Season.label).order_by(Season.label)
            )
        ).all()
    assert [tuple(r) for r in rows] == [("2023-24", 20), ("2024-25", 20)]


async def scarborough_games() -> list[Match]:
    async with get_sessionmaker()() as session:
        home_id = select(Team.id).where(Team.name == "Scarborough Athletic").scalar_subquery()
        return list(
            await session.scalars(select(Match).where(Match.home_team_id == home_id).order_by(Match.occurrence))
        )


async def test_repeated_pairing_keeps_both_games(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    """A pairing listed again after a scored game is a further game, stable across syncs (matches spec)."""
    fa_cup = [c for c in fixture_competitions if c.name == "FA Cup"]
    await sync(fa_cup, fixture_teams)
    first = await scarborough_games()
    assert [(m.occurrence, m.stage, m.matchday, m.home_score, m.away_score) for m in first] == [
        (1, Stage.ROUND, 1, 1, 1),
        (2, Stage.ROUND, 1, 2, 4),
    ]
    await sync(fa_cup, fixture_teams)
    assert [m.id for m in await scarborough_games()] == [m.id for m in first]


async def test_postponed_pairing_listed_twice_is_one_game(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    """A pairing listed again after an unscored listing is the same game rescheduled (matches spec)."""
    path = fresh_db / "england/2023-24/facup.txt"
    path.write_text(path.read_text(encoding="utf-8").replace("1-1 (1-0)", "[postponed]"), encoding="utf-8")
    await sync([c for c in fixture_competitions if c.name == "FA Cup"], fixture_teams)
    [game] = await scarborough_games()
    assert (game.occurrence, game.status, game.home_score, game.away_score) == (1, MatchStatus.COMPLETED, 2, 4)
    assert game.kickoff_utc == datetime(2023, 12, 12, 19, 45, tzinfo=UTC)
    assert game.original_kickoff_utc == datetime(2023, 11, 4, 15, 0, tzinfo=UTC)



async def test_date_only_kickoff_keeps_its_date(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    """A fixture with a date but no time is stored at midnight UTC on that date, even in summer time,
    and its time appearing later on the same day is not a move."""
    path = fresh_db / "england/2024-25/1-premierleague.txt"
    timed = path.read_text(encoding="utf-8")
    path.write_text(timed.replace("    20:00  Manchester United FC", "           Manchester United FC"), encoding="utf-8")
    competitions = [
        c.model_copy(update={"seasons": [s.model_copy(update={"json_file": None}) for s in c.seasons]})
        for c in fixture_competitions
        if c.name == "Premier League"
    ]
    await sync(competitions, fixture_teams)
    match = await match_by("Manchester United", "Fulham", Stage.LEAGUE)
    assert match.kickoff_utc == datetime(2024, 8, 16, 0, 0, tzinfo=UTC)

    path.write_text(timed, encoding="utf-8")
    await sync(competitions, fixture_teams)
    match = await match_by("Manchester United", "Fulham", Stage.LEAGUE)
    assert match.kickoff_utc == datetime(2024, 8, 16, 19, 0, tzinfo=UTC)
    assert match.original_kickoff_utc is None


async def test_earlier_local_midnight_placeholder_is_not_a_move(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    """Rows written by earlier syncs (date-only kickoff at local midnight, and that value recorded as
    the original kickoff once the time appeared) are corrected on the next sync."""
    competitions = [c for c in fixture_competitions if c.name == "Premier League"]
    await sync(competitions, fixture_teams)
    legacy = datetime(2024, 8, 15, 23, 0, tzinfo=UTC)  # midnight in London on 16 August
    async with get_sessionmaker()() as session, session.begin():
        match = await session.get(Match, (await match_by("Manchester United", "Fulham", Stage.LEAGUE)).id)
        assert match is not None
        match.original_kickoff_utc = legacy
    await sync(competitions, fixture_teams)
    match = await match_by("Manchester United", "Fulham", Stage.LEAGUE)
    assert (match.kickoff_utc, match.original_kickoff_utc) == (datetime(2024, 8, 16, 19, 0, tzinfo=UTC), None)


async def fa_cup_ids() -> dict[tuple[str, str, int], tuple[uuid.UUID, Stage]]:
    async with get_sessionmaker()() as session:
        home, away = Team.__table__.alias("home"), Team.__table__.alias("away")
        rows = await session.execute(
            select(home.c.name, away.c.name, Match.occurrence, Match.id, Match.stage)
            .join(home, home.c.id == Match.home_team_id)
            .join(away, away.c.id == Match.away_team_id)
        )
        return {(h, a, o): (i, s) for h, a, o, i, s in rows}


async def test_relabelled_round_keeps_its_matches(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    """A round renamed in the source moves its matches to the new stage, same UUIDs (ingestion spec)."""
    fa_cup = [c for c in fixture_competitions if c.name == "FA Cup"]
    await sync(fa_cup, fixture_teams)
    before = await fa_cup_ids()
    path = fresh_db / "england/2023-24/facup.txt"
    path.write_text(path.read_text(encoding="utf-8").replace("▪ Semifinals", "▪ Round 5"), encoding="utf-8")
    await sync(fa_cup, fixture_teams)
    after = await fa_cup_ids()
    assert {k: v[0] for k, v in after.items()} == {k: v[0] for k, v in before.items()}
    assert after[("Coventry City", "Manchester United", 1)][1] is Stage.ROUND


async def test_match_removed_from_source_is_deleted(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    """A match the source no longer lists is deleted with its verification status (ingestion spec)."""
    fa_cup = [c for c in fixture_competitions if c.name == "FA Cup"]
    await sync(fa_cup, fixture_teams)
    before = await fa_cup_ids()
    final_id = before[("Manchester City", "Manchester United", 1)][0]
    async with get_sessionmaker()() as session, session.begin():
        session.add(
            MatchVerification(
                match_id=final_id, reference=VerificationReference.WIKIPEDIA,
                status=VerificationStatus.VERIFIED, checked_at=datetime.now(UTC),
            )
        )
    path = fresh_db / "england/2023-24/facup.txt"
    text = path.read_text(encoding="utf-8")
    path.write_text(text[: text.index("▪ Final")], encoding="utf-8")
    await sync(fa_cup, fixture_teams)
    after = await fa_cup_ids()
    assert ("Manchester City", "Manchester United", 1) not in after
    assert {k: v[0] for k, v in after.items()} == {k: v[0] for k, v in before.items() if k[0] != "Manchester City"}
    async with get_sessionmaker()() as session:
        assert await session.scalar(select(func.count()).select_from(MatchVerification)) == 0
        assert await session.scalar(select(func.count()).select_from(ExternalRef).where(ExternalRef.entity_id == final_id)) == 0


async def test_alias_moved_to_another_club_follows_it(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    """An alias wrongly listed under one club and later moved to its own entry takes its matches
    along; the club it left keeps its row and loses that season."""
    dortmund = next(t for t in fixture_teams if t.name == "Borussia Dortmund")
    merged = [
        t.model_copy(update={"openfootball": [*t.openfootball, *dortmund.openfootball]}) if t.name == "Arsenal" else t
        for t in fixture_teams
        if t is not dortmund
    ]
    await sync(fixture_competitions, merged)
    async with get_sessionmaker()() as session:
        arsenal = await session.scalar(select(Team).where(Team.name == "Arsenal"))
        assert arsenal is not None
        seasons_before = await session.scalar(select(func.count()).select_from(TeamSeason).where(TeamSeason.team_id == arsenal.id))

    await sync(fixture_competitions, fixture_teams)
    async with get_sessionmaker()() as session:
        moved = await session.scalar(select(Team).where(Team.name == "Borussia Dortmund"))
        assert moved is not None and moved.id != arsenal.id
        assert (await session.scalar(select(func.count()).select_from(Match).where(Match.home_team_id == moved.id)) or 0) > 0
        seasons_after = await session.scalar(select(func.count()).select_from(TeamSeason).where(TeamSeason.team_id == arsenal.id))
        refs = set(await session.scalars(select(ExternalRef.source_id).where(ExternalRef.entity_id == arsenal.id)))
    assert seasons_after is not None and seasons_before is not None and seasons_after < seasons_before
    assert not refs & set(dortmund.openfootball)


async def test_corrected_qid_replaces_the_old_one(
    fresh_db: Path, fixture_competitions: list[CompetitionSeed], fixture_teams: list[TeamSeed]
) -> None:
    await sync(fixture_competitions, fixture_teams)
    corrected = [t.model_copy(update={"wikidata": "Q999999999"}) if t.name == "Arsenal" else t for t in fixture_teams]
    await sync(fixture_competitions, corrected)
    async with get_sessionmaker()() as session:
        arsenal = await session.scalar(select(Team).where(Team.name == "Arsenal"))
        assert arsenal is not None
        qids = set(await session.scalars(select(ExternalRef.source_id).where(ExternalRef.entity_id == arsenal.id, ExternalRef.source == "wikidata")))
    assert qids == {"Q999999999"}
