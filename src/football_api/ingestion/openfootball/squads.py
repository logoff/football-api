"""Squad-file parsers for the two observed formats.

`more` (worldcup/more, club-worldcup/more)::

    == Paris Saint-Germain (FRA)     # 27 Players
           1, Gianluigi DONNARUMMA (ITA),    GK,  b. 1999/02/25
           5, MARQUINHOS (BRA),              DF,  b. 1994/05/14

`per-team` (euro/…/squads/*.txt, copa-america/…/squads/*.txt)::

    =  Spain - Euro 2024
      1,  David Raya,                        GK,      5/0  , b. 1995,  Arsenal F.C. (ENG)
"""

import re
from dataclasses import dataclass
from datetime import date

from football_api.ingestion.openfootball.names import PersonName, split_capitalised

_MORE_TEAM_RE = re.compile(r"^==\s+(?P<team>.+?)\s*(?:#.*)?$")
_MORE_PLAYER_RE = re.compile(
    # The shirt number and its comma are absent before 1954 (`Jimmy DOUGLAS, GK, b. 1898/01/12`).
    r"^\s*(?:(?P<num>\d+)\s*,)?\s*(?P<name>[^,]+?)\s*(?:\((?P<nat>[A-Z]{3})\))?\s*,\s*(?P<pos>[A-Z]{2})\s*,"
    r"\s*b\.\s*(?P<y>\d{4})(?:/(?P<m>\d{2})/(?P<d>\d{2}))?"
)
_PER_TEAM_HEADER_RE = re.compile(r"^=\s+(?P<team>.+?)\s+-\s+.+$")
_PER_TEAM_PLAYER_RE = re.compile(
    r"^\s*(?P<num>\d+)?\s*,\s*(?P<name>[^,]+?)\s*,\s*(?P<pos>[A-Z]{2})\s*,[^,]*,\s*b\.\s*(?P<y>\d{4})"
)


@dataclass(frozen=True)
class SquadPlayer:
    team: str
    name: PersonName
    shirt_number: int | None
    position: str
    birth_year: int
    dob: date | None
    nationality_code: str | None


def parse_more_squads(text: str) -> list[SquadPlayer]:
    players: list[SquadPlayer] = []
    team: str | None = None
    for line in text.splitlines():
        if m := _MORE_TEAM_RE.match(line):
            team = m.group("team")
            continue
        m = _MORE_PLAYER_RE.match(line)
        if not m or team is None:
            continue
        year = int(m.group("y"))
        dob = date(year, int(m.group("m")), int(m.group("d"))) if m.group("m") else None
        players.append(
            SquadPlayer(
                team=team,
                name=split_capitalised(m.group("name")),
                shirt_number=int(m.group("num")) if m.group("num") else None,
                position=m.group("pos"),
                birth_year=year,
                dob=dob,
                nationality_code=m.group("nat"),
            )
        )
    return players


def parse_per_team_squad(text: str) -> list[SquadPlayer]:
    team: str | None = None
    players: list[SquadPlayer] = []
    for line in text.splitlines():
        if team is None and (m := _PER_TEAM_HEADER_RE.match(line.strip())):
            team = m.group("team")
            continue
        m = _PER_TEAM_PLAYER_RE.match(line)
        if not m or team is None:
            continue
        players.append(
            SquadPlayer(
                team=team,
                name=PersonName(display=m.group("name")),
                shirt_number=int(m.group("num")) if m.group("num") else None,
                position=m.group("pos"),
                birth_year=int(m.group("y")),
                dob=None,
                nationality_code=None,
            )
        )
    return players
