"""Reader for openfootball/football.json mirrors.

A mirror is used only when it is *current* for the season: same number of matches as
the text file, at least as many results, and no impossible values (e.g. a level
penalty shootout). Otherwise the caller falls back to the text file.
"""

import json
import re
from datetime import date, time
from pathlib import Path
from typing import Any, cast

from football_api.domain.enums import DecidedBy, MatchStatus
from football_api.ingestion.openfootball.text_parser import ParsedMatch, ParsedScore

_STATUS = {"awarded": MatchStatus.COMPLETED, "postponed": MatchStatus.POSTPONED, "cancelled": MatchStatus.CANCELLED}


def _pair(score: dict[str, Any], key: str) -> tuple[int, int] | None:
    value = score.get(key)
    if isinstance(value, list) and len(cast(list[Any], value)) == 2:
        home, away = cast(list[Any], value)
        if isinstance(home, int) and isinstance(away, int):
            return home, away
    return None


def _score(raw: dict[str, Any]) -> ParsedScore | None:
    score = cast(dict[str, Any], raw.get("score") or {})
    ft, et, pens = _pair(score, "ft"), _pair(score, "et"), _pair(score, "p")
    if ft is None:
        return None
    final = et or ft
    if pens:
        return ParsedScore(final[0], final[1], DecidedBy.PENALTIES, pens[0], pens[1])
    return ParsedScore(final[0], final[1], DecidedBy.EXTRA_TIME if et else DecidedBy.REGULAR)


def read_json(path: Path) -> list[ParsedMatch]:
    data = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    matches: list[ParsedMatch] = []
    for i, raw in enumerate(cast(list[dict[str, Any]], data["matches"]), 1):
        hh, mm = (int(x) for x in re.split(r"[:.]", raw["time"])[:2]) if raw.get("time") else (None, None)
        score = _score(raw)
        status = _STATUS.get(cast(str, raw.get("status") or ""))
        matches.append(
            ParsedMatch(
                line_no=i,
                round_label=raw["round"],
                day=date.fromisoformat(raw["date"]),
                kickoff=time(hh, mm) if hh is not None and mm is not None else None,
                utc_offset=None,
                home=raw["team1"],
                away=raw["team2"],
                score=score,
                status=status or (MatchStatus.COMPLETED if score else MatchStatus.SCHEDULED),
            )
        )
    return matches


def is_current(json_matches: list[ParsedMatch], text_matches: list[ParsedMatch]) -> bool:
    if len(json_matches) != len(text_matches):
        return False
    if sum(m.score is not None for m in json_matches) < sum(m.score is not None for m in text_matches):
        return False
    for m in json_matches:
        if m.status is MatchStatus.COMPLETED and m.score is None:
            return False
        if m.score and m.score.decided_by is DecidedBy.PENALTIES and m.score.home_pens == m.score.away_pens:
            return False
    return True
