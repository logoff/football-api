"""Comparison of a match's stored events with a Wikipedia line-up table (verify-match-events).

Players are paired within one side by name, then by shirt number (D3); line-ups, substitutions
and cards are then compared by paired player (D2). Only differences come out, as text for the
log; nothing of the reference is kept.
"""

import re
import unicodedata
from difflib import SequenceMatcher
from collections.abc import Sequence
from dataclasses import dataclass, field

from football_api.domain.enums import CardKind
from football_api.ingestion.wikipedia import LineupRow, Minute

CARDS_FROM_YEAR = 1970  # the first World Cup with cards; earlier cautions are recorded unevenly
# Words too common in names to pair two players on their own.
_PARTICLES = frozenset(
    "al el de da das do dos du van von der den di del della la le ben bin abu ibn jr junior filho neto mc mac".split()
)
_CARD_MARK = {CardKind.YELLOW: "Y", CardKind.SECOND_YELLOW: "2Y", CardKind.RED: "R"}


@dataclass
class StoredSide:
    """One side's stored events, by player name as the source spells it."""

    starters: list[str] = field(default_factory=lambda: list[str]())
    substitutes: list[str] = field(default_factory=lambda: list[str]())  # came on
    substitutions: list[tuple[str, str, Minute]] = field(default_factory=lambda: list[tuple[str, str, Minute]]())  # off, on
    cards: list[tuple[str, CardKind, Minute]] = field(default_factory=lambda: list[tuple[str, CardKind, Minute]]())
    numbers: dict[str, int] = field(default_factory=lambda: dict[str, int]())  # shirt numbers from the squad


# Letters NFKD doesn't fold to ASCII.
_LETTERS = str.maketrans({"ı": "i", "ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ð": "d", "þ": "th", "æ": "ae", "Æ": "AE", "ß": "ss", "œ": "oe"})
# German umlauts are also written with an `e`: Hügi, HUEGI.
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})
SIMILAR = 0.7  # least similarity of two names for a close spelling (`_similarity`)


def words(name: str, *, umlauts: bool = False) -> list[str]:
    """Lowercase ASCII words: accents folded, punctuation and the captain mark dropped."""
    name = name.translate(_UMLAUTS) if umlauts else name
    folded = unicodedata.normalize("NFKD", name.translate(_LETTERS)).encode("ascii", "ignore").decode().lower()
    folded = re.sub(r"\(\s*c\s*\)|\[\s*c\s*\]", " ", folded)
    return [w for w in re.split(r"[^a-z]+", folded) if w]


def _spellings(name: str) -> set[str]:
    return {"".join(words(name)), "".join(words(name, umlauts=True))}


def _similarity(a: str, b: str) -> float:
    """How alike two names are: each word of the shorter name against its closest word in the
    other, averaged (`Jose JOVEL` and `José Francisco Jovel` 1.0, `Oleg GUSEV` and `Oleh Husyev` 0.74)."""
    wa = [w for w in words(a, umlauts=True) if w not in _PARTICLES]
    wb = [w for w in words(b, umlauts=True) if w not in _PARTICLES]
    if not wa or not wb:
        return 0.0
    short, long = sorted((wa, wb), key=len)
    return sum(max(SequenceMatcher(None, x, y).ratio() for y in long) for x in short) / len(short)


def _unique_pairs(left: Sequence[str], right: Sequence[int], key_l: dict[str, set[str]], key_r: dict[int, set[str]]) -> dict[str, int]:
    """Pairs whose keys meet exactly one candidate on each side."""
    pairs: dict[str, int] = {}
    for name in left:
        candidates = [r for r in right if key_l[name] & key_r[r]]
        if len(candidates) == 1:
            back = [n for n in left if key_l[n] & key_r[candidates[0]]]
            if back == [name]:
                pairs[name] = candidates[0]
    return pairs


def pair_players(names: Sequence[str], rows: Sequence[LineupRow], numbers: dict[str, int]) -> dict[str, int]:
    """Stored name → index of its row (D3): equal names (ignoring case, accents, punctuation and
    spaces), then a single shared word, then the same shirt number, then a single close spelling."""
    pairs: dict[str, int] = {}

    def left() -> tuple[list[str], list[int]]:
        used = set(pairs.values())
        return [n for n in names if n not in pairs], [i for i in range(len(rows)) if i not in used]

    full = {n: _spellings(n) for n in names}
    full_r = {i: _spellings(r.name) for i, r in enumerate(rows)}
    pairs |= _unique_pairs(*left(), full, full_r)
    shared = {n: set(words(n)) - _PARTICLES for n in names}
    shared_r = {i: set(words(r.name)) - _PARTICLES for i, r in enumerate(rows)}
    pairs |= _unique_pairs(*left(), shared, shared_r)
    numbered = {n: {str(numbers[n])} if n in numbers else set[str]() for n in names}
    numbered_r = {i: {str(r.number)} if r.number is not None else set[str]() for i, r in enumerate(rows)}
    pairs |= _unique_pairs(*left(), numbered, numbered_r)
    # Then the closest spellings, each the other's closest, best first.
    rest, rest_r = left()
    scores = sorted(((_similarity(n, rows[i].name), n, i) for n in rest for i in rest_r), reverse=True)
    best_n = {n: max((sc for sc, m, _ in scores if m == n), default=0.0) for n in rest}
    best_r = {i: max((sc for sc, _, j in scores if j == i), default=0.0) for i in rest_r}
    taken: set[int] = set()
    for score, name, i in scores:
        if score < SIMILAR:
            break
        if name in pairs or i in taken or score < best_n[name] or score < best_r[i]:
            continue
        # A tie for either player leaves them unpaired: the names don't tell who is who.
        if sum(1 for sc, m, j in scores if sc == score and (m == name) != (j == i)) == 0:
            pairs[name] = i
            taken.add(i)
    return pairs


def close(a: Minute | None, b: Minute | None) -> bool:
    """Minutes agree within one; the added minute counts only when both have one (D2)."""
    if a is None or b is None:
        return True
    if a[1] is not None and b[1] is not None:
        return a[0] == b[0] and abs(a[1] - b[1]) <= 1
    if a[1] is not None or b[1] is not None:
        # Extra time written as added time on one side: `90+8'` and `98'`.
        (m, added), other = (a, b[0]) if a[1] is not None else (b, a[0])
        return abs(m - other) <= 1 or abs(m + (added or 0) - other) <= 1
    return abs(a[0] - b[0]) <= 1


def _fmt_minute(m: Minute | None) -> str:
    return "?" if m is None else f"{m[0]}+{m[1]}'" if m[1] is not None else f"{m[0]}'"


def _fmt_cards(cards: Sequence[tuple[CardKind, Minute | None]]) -> str:
    return ", ".join(f"{_CARD_MARK[k]} {_fmt_minute(m)}" for k, m in cards) or "none"


def _same_cards(a: Sequence[tuple[CardKind, Minute | None]], b: Sequence[tuple[CardKind, Minute | None]]) -> bool:
    rest = list(b)
    for kind, minute in a:
        match = next((c for c in rest if c[0] is kind and close(minute, c[1])), None)
        if match is None:
            return False
        rest.remove(match)
    return not rest


def _role(starter: bool, came_on: bool) -> str:
    return "starter" if starter else "substitute" if came_on else "not playing"


def compare_side(stored: StoredSide, rows: Sequence[LineupRow], *, cards: bool, substitutions: bool) -> list[str]:
    """The differences between one side's stored events and its line-up table, one text each.
    Without `substitutions`, only the starters are compared; without `cards`, no cards."""
    names = list(dict.fromkeys([*stored.starters, *stored.substitutes, *(s for o, i, _ in stored.substitutions for s in (o, i)), *(n for n, _, _ in stored.cards)]))
    pairs = pair_players(names, rows, stored.numbers)
    paired_rows = set(pairs.values())
    off = {o: m for o, _, m in stored.substitutions}
    on = {i: m for _, i, m in stored.substitutions}
    by_player: dict[str, list[tuple[CardKind, Minute | None]]] = {}
    for name, kind, minute in stored.cards:
        by_player.setdefault(name, []).append((kind, minute))
    diffs: list[str] = []
    for name in names:
        role = _role(name in stored.starters, name in stored.substitutes or name in on)
        index = pairs.get(name)
        if index is None:
            if role == "starter" or (role == "substitute" and substitutions):
                diffs.append(f"{name}: {role}, not in wikipedia's line-up")
            elif cards and by_player.get(name):
                diffs.append(f"{name}: cards {_fmt_cards(by_player[name])}, not in wikipedia's line-up")
            continue
        row = rows[index]
        theirs = _role(row.starter, row.on is not None)
        if substitutions:
            if role != theirs:
                diffs.append(f"{name}: {role} vs {theirs}")
            if (name in off) != (row.off is not None) or not close(off.get(name), row.off):
                diffs.append(f"{name}: off {_fmt_minute(off[name]) if name in off else 'never'} vs {_fmt_minute(row.off) if row.off else 'never'}")
            if role == theirs == "substitute" and not close(on.get(name), row.on):
                diffs.append(f"{name}: on {_fmt_minute(on.get(name))} vs {_fmt_minute(row.on)}")
        elif (role == "starter") != row.starter:
            diffs.append(f"{name}: {role} vs {'starter' if row.starter else 'substitute'}")
        if cards and not _same_cards(by_player.get(name, []), row.cards):
            diffs.append(f"{name}: cards {_fmt_cards(by_player.get(name, []))} vs {_fmt_cards(row.cards)}")
    for i, row in enumerate(rows):
        if i in paired_rows:
            continue
        if row.starter or (row.on is not None and substitutions):
            diffs.append(f"{row.name}: only in wikipedia's line-up, as {_role(row.starter, True)}")
        elif cards and row.cards:
            diffs.append(f"{row.name}: cards none vs {_fmt_cards(row.cards)}")
    return diffs


def compare_match(
    home: StoredSide, away: StoredSide, lineups: tuple[Sequence[LineupRow], Sequence[LineupRow]], *, year: int
) -> tuple[list[str], list[str]]:
    """Each side's differences (D2). Cards count from `CARDS_FROM_YEAR`, and only when the table
    records any; substitutions only when it records any: some tables list the players alone."""
    rows = [r for side in lineups for r in side]
    cards = year >= CARDS_FROM_YEAR and any(r.cards for r in rows)
    substitutions = any(r.on is not None or r.off is not None for r in rows)
    return (
        compare_side(home, lineups[0], cards=cards, substitutions=substitutions),
        compare_side(away, lineups[1], cards=cards, substitutions=substitutions),
    )
