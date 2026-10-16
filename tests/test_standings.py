"""Standings computation from hand-made results (standings spec)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from football_api.domain.enums import Stage
from football_api.ingestion.seeds import Criterion, Points, StandingsEra
from football_api.standings import Row, Rules, Settled, TableMatch, group_of, phase_of, rank, split_tables

T0 = datetime(2031, 8, 1, 15, tzinfo=UTC)
NAMES: dict[uuid.UUID, str] = {}


def team(name: str) -> uuid.UUID:
    tid = uuid.uuid5(uuid.NAMESPACE_DNS, name)
    NAMES[tid] = name
    return tid


A, B, C, D = team("Alpha"), team("Beta"), team("Gamma"), team("Delta")


def m(home: uuid.UUID, away: uuid.UUID, score: str | None, day: int = 0, stage: Stage = Stage.LEAGUE, label: str | None = None) -> TableMatch:
    hs, as_ = (int(x) for x in score.split("-")) if score else (None, None)
    return TableMatch(home, away, hs, as_, T0 + timedelta(days=day), stage, label)


def rules(*tiebreakers: Criterion, win: int = 3, ppg: bool = False) -> Rules:
    era = StandingsEra.model_validate({"from": 2000, "points": Points(win=win, draw=1), "tiebreakers": list(tiebreakers)})
    return Rules(era, points_per_game=ppg)


def order(rows: list[Row]) -> list[str]:
    return [NAMES[r.team] for r in rows]


def test_row_totals() -> None:
    results = [m(A, B, "3-1"), m(B, A, "2-2"), m(A, C, "0-1")]
    rows = {r.team: r for r in rank([A, B, C], results, rules("goal_difference"), name=NAMES.__getitem__)}
    a = rows[A]
    assert (a.played, a.won, a.drawn, a.lost, a.goals_for, a.goals_against, a.goal_difference, a.points) == (3, 1, 1, 1, 5, 4, 1, 4)


def test_unplayed_matches_dont_count() -> None:
    rows = rank([A, B], [m(A, B, "1-0"), m(B, A, None)], rules(), name=NAMES.__getitem__)
    assert [(r.played, r.points) for r in rows] == [(1, 3), (1, 0)]


def test_two_points_for_a_win() -> None:
    rows = rank([A, B, C], [m(A, B, "1-0"), m(A, C, "1-1")], rules(win=2), name=NAMES.__getitem__)
    assert rows[0].points == 3


def test_goal_difference_first_ignores_head_to_head() -> None:
    # A and B level on 6 points; B beat A, but A has the better goal difference.
    results = [m(A, C, "5-0"), m(A, D, "4-0"), m(B, A, "1-0"), m(B, C, "0-1"), m(B, D, "1-0"), m(C, D, "0-0")]
    ranked = rank([A, B, C, D], results, rules("goal_difference", "goals_for", "h2h_points"), name=NAMES.__getitem__)
    assert order(ranked)[:2] == ["Alpha", "Beta"]


def test_head_to_head_first() -> None:
    results = [m(A, C, "5-0"), m(A, D, "4-0"), m(B, A, "1-0"), m(B, C, "0-1"), m(B, D, "1-0"), m(C, D, "0-0")]
    ranked = rank([A, B, C, D], results, rules("h2h_points", "h2h_goal_difference", "goal_difference"), name=NAMES.__getitem__)
    assert order(ranked)[:2] == ["Beta", "Alpha"]


def test_head_to_head_among_three() -> None:
    """A three-way tie is split by the matches among the three teams only."""
    # A, B, C each beat one another in a cycle and beat D. Among A, B, C: A 2-0 B, B 1-0 C,
    # C 1-0 A, so A has the best head-to-head goal difference (+1), then C (0), then B (-1).
    results = [m(A, B, "2-0"), m(B, C, "1-0"), m(C, A, "1-0"), m(A, D, "1-0"), m(B, D, "1-0"), m(C, D, "1-0")]
    ranked = rank([A, B, C, D], results, rules("h2h_points", "h2h_goal_difference"), name=NAMES.__getitem__)
    assert order(ranked) == ["Alpha", "Gamma", "Beta", "Delta"] and not any(r.tied for r in ranked)


def test_reapply_head_to_head_among_a_smaller_tied_set() -> None:
    """UEFA: teams still level after the head-to-head criteria among three restart them among themselves."""
    # A, B, C finish on 6 points. Among the three, A takes 6 points and B and C 3 each, with equal
    # goal difference among the three (-2). Between B and C alone, B is +1.
    results = [
        m(A, B, "3-0"), m(A, C, "1-0"), m(B, C, "3-1"), m(C, B, "1-0"),
        m(D, A, "1-0"), m(B, D, "1-0"), m(C, D, "1-0"),
    ]  # fmt: skip
    plain = rank([A, B, C, D], results, rules("h2h_points", "h2h_goal_difference"), name=NAMES.__getitem__)
    assert order(plain)[:3] == ["Alpha", "Beta", "Gamma"] and plain[1].tied and plain[2].tied
    reapplied = rank([A, B, C, D], results, rules("h2h_points", "h2h_reapply", "h2h_goal_difference"), name=NAMES.__getitem__)
    assert order(reapplied)[:3] == ["Alpha", "Beta", "Gamma"] and not any(r.tied for r in reapplied)


def test_points_per_game() -> None:
    # A: 7 points in 4 games (1.75); B: 6 points in 3 games (2.0).
    results = [m(A, C, "1-0"), m(A, D, "1-0"), m(A, B, "0-0"), m(D, A, "1-0"), m(B, C, "1-0"), m(B, D, "1-0")]
    assert order(rank([A, B, C, D], results, rules(ppg=True), name=NAMES.__getitem__))[:2] == ["Beta", "Alpha"]


def test_adjustment_changes_points_and_order() -> None:
    results = [m(A, C, "1-0"), m(B, C, "0-0")]
    # Without the deduction A leads on 3 points; with -3 it drops below B and C (1 point each).
    ranked = rank([A, B, C], results, rules("goal_difference"), adjustments={A: -3}, name=NAMES.__getitem__)
    assert order(ranked)[-1] == "Alpha"
    assert ranked[-1].points == 0 and ranked[-1].adjustment == -3


def test_level_after_every_criterion_is_tied_and_settled_by_curated_order() -> None:
    results = [m(A, B, "1-1"), m(C, D, "0-0")]
    plain = rank([A, B, C, D], results, rules("goal_difference", "goals_for"), name=NAMES.__getitem__)
    assert order(plain)[:2] == ["Alpha", "Beta"] and plain[0].tied and plain[1].tied
    settled = rank(
        [A, B, C, D], results, rules("goal_difference", "goals_for"), settled=[Settled((B, A))], name=NAMES.__getitem__
    )
    assert order(settled)[:2] == ["Beta", "Alpha"] and settled[0].tied


def test_goal_ratio() -> None:
    # Same points; A 4-2 (ratio 2.0), B 2-0 (infinite) -> B higher; goal difference would tie them.
    results = [m(A, C, "4-2"), m(B, D, "2-0")]
    assert order(rank([A, B, C, D], results, rules("goal_ratio"), name=NAMES.__getitem__))[:2] == ["Beta", "Alpha"]


def test_opponents_points() -> None:
    # A and B both beat one opponent; A's opponent (C) has more points than B's (D).
    results = [m(A, C, "1-0"), m(B, D, "1-0"), m(C, D, "1-0")]
    ranked = rank([A, B, C, D], results, rules("goal_difference", "goals_for", "opponents_points"), name=NAMES.__getitem__)
    assert order(ranked)[:2] == ["Alpha", "Beta"]


@pytest.mark.parametrize(
    ("label", "group", "phase"),
    [
        ("Group A", "A", 1),
        ("Gruppe 3", "3", 1),
        ("First stage / Group B", "B", 1),
        ("First Stage, Group L", "L", 1),
        ("Group Matches / Group 1", "1", 1),
        ("Group Stage / Group H", "H", 1),
        ("Second Round / Group C", "C", 2),
        ("Group, Matchday 4", None, 1),
        ("League, Matchday 2", None, 1),
    ],
)
def test_group_and_phase_from_label(label: str, group: str | None, phase: int) -> None:
    assert (group_of(label), phase_of(label)) == (group, phase)


def test_split_named_groups_second_round_and_league() -> None:
    E, F = team("Epsilon"), team("Zeta")
    matches = [
        m(A, B, "1-0", stage=Stage.GROUP, label="Group A"),
        m(C, D, "1-0", stage=Stage.GROUP, label="Group B"),
        m(A, C, "2-0", stage=Stage.GROUP, label="Second Round / Group A"),
        m(E, F, "0-0", stage=Stage.LEAGUE, label="League, Matchday 1"),
        m(A, D, "0-0", stage=Stage.FINAL, label="Final"),
    ]
    keys = [(t.key.stage, t.key.phase, t.key.group, len(t.matches)) for t in split_tables(matches)]
    assert keys == [(Stage.LEAGUE, 1, None, 1), (Stage.GROUP, 1, "A", 1), (Stage.GROUP, 1, "B", 1), (Stage.GROUP, 2, "A", 1)]


def test_unnamed_groups_are_the_teams_that_played_each_other() -> None:
    E, F = team("Epsilon"), team("Zeta")
    matches = [
        m(C, D, "1-0", day=2, stage=Stage.GROUP, label="Group, Matchday 1"),
        m(A, B, "1-0", day=1, stage=Stage.GROUP, label="Group, Matchday 1"),
        m(B, E, "1-0", day=3, stage=Stage.GROUP, label="Group, Matchday 2"),
        m(D, F, "0-0", day=4, stage=Stage.GROUP, label="Group, Matchday 2"),
    ]
    tables = split_tables(matches)
    assert [(t.key.group, {NAMES[x] for x in t.teams}) for t in tables] == [
        (None, {"Alpha", "Beta", "Epsilon"}),  # earliest kickoff first
        (None, {"Gamma", "Delta", "Zeta"}),
    ]


def test_unnamed_match_joins_its_named_group() -> None:
    matches = [m(A, B, "1-0", stage=Stage.GROUP, label="Group A"), m(B, A, "2-2", stage=Stage.GROUP, label="Group, Matchday 4")]
    tables = split_tables(matches)
    assert [(t.key.group, len(t.matches)) for t in tables] == [("A", 2)]


def test_play_off_order_overrides_tie_breakers_for_teams_level_on_points() -> None:
    # A and B level on points; B is ahead on goal difference, but A won a play-off.
    results = [m(A, C, "1-0"), m(B, C, "3-0")]
    ranked = rank([A, B, C], results, rules("goal_difference"), settled=[Settled((A, B))], name=NAMES.__getitem__)
    assert order(ranked)[:2] == ["Alpha", "Beta"] and ranked[0].tied and ranked[1].tied


def test_awarded_match_with_a_level_score_and_a_winner() -> None:
    """The LFP gave Lyon the win at Bastia but kept the 0-0: the win counts, the goals don't."""
    awarded = TableMatch(A, B, 0, 0, T0, Stage.LEAGUE, None, winner=B)
    rows = {r.team: r for r in rank([A, B], [awarded], rules("goal_difference"), name=NAMES.__getitem__)}
    assert (rows[B].won, rows[B].points, rows[B].goals_for) == (1, 3, 0)
    assert (rows[A].lost, rows[A].points) == (1, 0)


def test_group_play_off_is_not_in_the_table() -> None:
    """1958: Northern Ireland and Czechoslovakia met again in a play-off listed under the group."""
    group = [
        m(A, B, "1-0", day=0, stage=Stage.GROUP, label="Group 1"),
        m(C, D, "2-2", day=0, stage=Stage.GROUP, label="Group 1"),
        m(A, C, "0-1", day=3, stage=Stage.GROUP, label="Group 1"),
        m(B, D, "1-1", day=3, stage=Stage.GROUP, label="Group 1"),
        m(A, D, "1-1", day=6, stage=Stage.GROUP, label="Group 1"),
        m(B, C, "0-0", day=6, stage=Stage.GROUP, label="Group 1"),
        m(A, B, "2-1", day=9, stage=Stage.GROUP, label="Group 1"),  # the play-off
    ]
    [table] = split_tables(group)
    assert len(table.matches) == 6


def test_home_and_away_groups_keep_both_legs() -> None:
    legs = [m(A, B, "1-0", stage=Stage.GROUP, label="Group A"), m(B, A, "2-0", day=7, stage=Stage.GROUP, label="Group A")]
    [table] = split_tables(legs)
    assert len(table.matches) == 2
