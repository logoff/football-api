"""Player-name normalisation. See design.md, "Players — squads first"."""

import re
import unicodedata
from dataclasses import dataclass

_UPPER_WORD_RE = re.compile(r"^[^a-z]*[A-Z][^a-z]*$")


@dataclass(frozen=True)
class PersonName:
    display: str
    given: str | None = None
    family: str | None = None


def _title(word: str) -> str:
    # Title-case each hyphen/apostrophe part: DEWSBURY-HALL → Dewsbury-Hall, N'GOLO → N'Golo.
    return re.sub(r"[^\W\d_]+", lambda m: m.group(0).capitalize(), word.lower())


def split_capitalised(raw: str) -> PersonName:
    """Split a capitalised-surname name (`Lionel MESSI`) without storing the capitals.

    Trailing all-caps words are the family name. A name written entirely in capitals
    (`MARQUINHOS`, `NUNO MENDES`) is a known-as name: display only, no split.
    """
    words = raw.split()
    family_start = len(words)
    while family_start > 0 and _UPPER_WORD_RE.match(words[family_start - 1]):
        family_start -= 1
    display = " ".join(_title(w) if _UPPER_WORD_RE.match(w) else w for w in words)
    if family_start == 0 or family_start == len(words):
        return PersonName(display=display)
    return PersonName(
        display=display,
        given=" ".join(words[:family_start]),
        family=" ".join(_title(w) for w in words[family_start:]),
    )


def fold(name: str) -> str:
    """Case- and accent-insensitive comparison key: `Suárez` == `SUAREZ`."""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", stripped.casefold()).strip()


def short_name_matches(short: str, full: str) -> bool:
    """True when `short` names the same person as `full`, aligned from the surname.

    Each token of `short`, right-aligned against `full`, must be equal after folding,
    or be an abbreviation (`La.`) of the corresponding token: `Koulibaly` and
    `La. Martínez` match `Kalidou Koulibaly` and `Lautaro Martínez`.
    """
    raw_tokens = short.split()
    short_tokens = [(fold(t), t.endswith(".")) for t in raw_tokens]
    short_tokens = [(t, abbrev) for t, abbrev in short_tokens if t]
    full_tokens = fold(full).split()
    if not short_tokens or len(short_tokens) > len(full_tokens):
        return False
    for (token, abbrev), target in zip(reversed(short_tokens), reversed(full_tokens)):
        if token != target and not (abbrev and target.startswith(token)):
            return False
    return True
