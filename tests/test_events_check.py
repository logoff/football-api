"""Pairing players and comparing a match's events with a line-up table (verify-match-events D2, D3)."""

from football_api.domain.enums import CardKind
from football_api.events_check import StoredSide, close, compare_match, compare_side, pair_players, words
from football_api.ingestion.wikipedia import LineupRow

Y, Y2, R = CardKind.YELLOW, CardKind.SECOND_YELLOW, CardKind.RED


def row(name: str, *, starter: bool = True, number: int | None = None, **kw: object) -> LineupRow:
    return LineupRow(name, number, starter, **kw)  # type: ignore[arg-type]


def test_words_fold_accents_letters_and_the_captain_mark() -> None:
    assert words("Sergej Milinković-Savić (c)") == ["sergej", "milinkovic", "savic"]
    assert words("Rıdvan Bolatlı") == ["ridvan", "bolatli"]
    assert words("Josef Hügi", umlauts=True) == ["josef", "huegi"]


def test_pairing_rules() -> None:
    rows = [
        row("Sergej Milinković-Savić"),  # accents and case
        row("Saad Al-Sheeb"),  # spaces and punctuation
        row("Josef Hügi"),  # umlaut written with an e
        row("Raphael Tracey"),  # close spelling
        row("Mazzola", number=18),  # another name altogether: the shirt number
        row("Ahmed Fathy"),
        row("Ahmed Hegazi"),
    ]
    names = ["Sergej MILINKOVIC-SAVIC", "SAAD ALSHEEB", "Sepp HUEGI", "Ralph TRACY", "Jose ALTAFINI", "AHMED HEGAZY", "AHMED FATHI"]
    pairs = pair_players(names, rows, {"Jose ALTAFINI": 18})
    assert {n: rows[i].name for n, i in pairs.items()} == {
        "Sergej MILINKOVIC-SAVIC": "Sergej Milinković-Savić",
        "SAAD ALSHEEB": "Saad Al-Sheeb",
        "Sepp HUEGI": "Josef Hügi",
        "Ralph TRACY": "Raphael Tracey",
        "Jose ALTAFINI": "Mazzola",
        "AHMED HEGAZY": "Ahmed Hegazi",
        "AHMED FATHI": "Ahmed Fathy",
    }


def test_different_players_stay_unpaired() -> None:
    assert pair_players(["Frank WALLACE"], [row("Robert Craddock")], {}) == {}


def test_minutes() -> None:
    assert close((18, None), (19, None))
    assert not close((18, None), (20, None))
    assert close((90, None), (90, 5))  # old matches have no added minute
    assert close((90, 8), (98, None))  # extra time written as added time
    assert close((90, 4), (90, 5)) and not close((90, 2), (90, 5))
    assert close(None, (12, None))


def _side(starters: list[str], **kw: object) -> StoredSide:
    return StoredSide(starters=starters, **kw)  # type: ignore[arg-type]


def test_agreeing_side_has_no_differences() -> None:
    stored = _side(["A ONE", "B TWO"], substitutes=["C THREE"], substitutions=[("B TWO", "C THREE", (60, None))], cards=[("A ONE", Y, (54, None)), ("A ONE", Y2, (74, None))])
    rows = [
        row("A One", cards=((Y, (54, None)), (Y2, (74, None)))),
        row("B Two", off=(61, None)),
        row("C Three", starter=False, on=(61, None)),
        row("D Four", starter=False),  # on the bench
    ]
    assert compare_side(stored, rows, cards=True, substitutions=True) == []


def test_each_kind_of_difference() -> None:
    stored = _side(["A ONE", "B TWO", "E FIVE"], substitutes=["C THREE"], substitutions=[("B TWO", "C THREE", (60, None))], cards=[("A ONE", Y, (73, None))])
    rows = [
        row("A One", cards=((Y, (54, None)), (Y2, (74, None)))),
        row("B Two", off=(70, None)),
        row("C Three", starter=False, on=(70, None)),
        row("F Six"),
        row("G Seven", starter=False, cards=((Y, (66, None)),)),  # booked on the bench
    ]
    assert compare_side(stored, rows, cards=True, substitutions=True) == [
        "A ONE: cards Y 73' vs Y 54', 2Y 74'",
        "B TWO: off 60' vs 70'",
        "E FIVE: starter, not in wikipedia's line-up",
        "C THREE: on 60' vs 70'",
        "F Six: only in wikipedia's line-up, as starter",
        "G Seven: cards none vs Y 66'",
    ]


def test_table_without_cards_or_substitutions_compares_starters_only() -> None:
    surnames = "Abbot Baker Cole Dean Ellis Fox Grant Hale Irwin Jones Kent".split()
    xi = [s.upper() for s in surnames]
    stored = _side(xi, substitutes=["SMITH"], substitutions=[(xi[0], "SMITH", (60, None))], cards=[(xi[1], Y, (10, None))])
    table = [row(s) for s in surnames]
    assert compare_match(stored, stored, (table, table), year=2006) == ([], [])


def test_cards_before_1970_are_not_compared() -> None:
    stored = _side(["A ONE"], cards=[("A ONE", Y, (70, None))])
    table = [row("A One"), row("B Two", cards=((R, (80, None)),))]
    assert compare_match(stored, _side(["B TWO"]), (table[:1], table[1:]), year=1966) == ([], [])
    assert compare_match(stored, _side(["B TWO"]), (table[:1], table[1:]), year=1970) == (
        ["A ONE: cards Y 70' vs none"],
        ["B TWO: cards none vs R 80'"],
    )
