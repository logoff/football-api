"""API smoke tests against the fixture-synced database (catalog and matches specs).

IDs are found the way a client finds them: by listing a resource and reading names.
"""

from datetime import UTC, datetime
from typing import Any, cast

import httpx
import pytest
from sqlalchemy import delete

from football_api.domain.enums import VerificationReference, VerificationStatus
from football_api.infra.db import get_sessionmaker
from football_api.infra.models import MatchVerification

pytestmark = pytest.mark.db

UNKNOWN = "00000000-0000-7000-8000-000000000000"


async def get(client: httpx.AsyncClient, url: str, status: int = 200) -> dict[str, Any]:
    resp = await client.get(url)
    assert resp.status_code == status, resp.text
    return cast(dict[str, Any], resp.json())


async def find(client: httpx.AsyncClient, url: str, name: str) -> dict[str, Any]:
    """Walk every page of a listing and return the item with this name."""
    cursor = ""
    while True:
        page = await get(client, f"{url}{'&' if '?' in url else '?'}limit=200{'&cursor=' + cursor if cursor else ''}")
        for item in page["data"]:
            if item.get("name") == name:
                return cast(dict[str, Any], item)
        if not page["next_cursor"]:
            raise AssertionError(f"{name} not found at {url}")
        cursor = cast(str, page["next_cursor"])


async def competition_id(client: httpx.AsyncClient, name: str) -> str:
    return cast(str, (await find(client, "/v1/competitions", name))["id"])


async def season_id(client: httpx.AsyncClient, competition: str) -> str:
    [season] = (await get(client, f"/v1/seasons?competition_id={await competition_id(client, competition)}"))["data"]
    return cast(str, season["id"])


async def team_id(client: httpx.AsyncClient, name: str) -> str:
    return cast(str, (await find(client, "/v1/teams", name))["id"])


def assert_error(body: dict[str, Any], code: str) -> None:
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)


async def test_healthz(client: httpx.AsyncClient) -> None:
    assert await get(client, "/healthz") == {"status": "ok"}


async def test_competitions_list_paginates(client: httpx.AsyncClient) -> None:
    first = await get(client, "/v1/competitions?limit=4")
    assert len(first["data"]) == 4 and first["next_cursor"]
    second = await get(client, f"/v1/competitions?limit=4&cursor={first['next_cursor']}")
    seen = [c["id"] for c in first["data"] + second["data"]]
    assert len(seen) == 8 and len(set(seen)) == 8
    assert second["next_cursor"] is None
    assert all("slug" not in c for c in first["data"])


async def test_competition_by_id_and_errors(client: httpx.AsyncClient) -> None:
    comp = await find(client, "/v1/competitions", "FIFA World Cup")
    assert (comp["team_kind"], comp["scope"], comp["country"]) == ("NATIONAL", "INTERCONTINENTAL", None)
    assert await get(client, f"/v1/competitions/{comp['id']}") == comp

    assert_error(await get(client, f"/v1/competitions/{UNKNOWN}", 404), "not_found")
    assert_error(await get(client, "/v1/competitions/premier-league", 422), "invalid_request")
    assert_error(await get(client, "/v1/seasons?competition_id=premier-league", 422), "invalid_request")
    assert_error(await get(client, "/v1/competitions?cursor=not-a-cursor", 422), "invalid_cursor")
    assert_error(await get(client, "/v1/competitions?limit=500", 422), "invalid_request")


async def test_competition_format_and_filter(client: httpx.AsyncClient) -> None:
    """catalog spec: `format` on competitions and the `?format=` filter."""
    cups = (await get(client, "/v1/competitions?format=CUP"))["data"]
    assert [c["name"] for c in cups] == ["FA Cup"]
    leagues = (await get(client, "/v1/competitions?format=LEAGUE"))["data"]
    assert sorted(c["name"] for c in leagues) == ["Bundesliga", "Premier League"]
    wc = await find(client, "/v1/competitions", "FIFA World Cup")
    assert wc["format"] == "TOURNAMENT"
    assert_error(await get(client, "/v1/competitions?format=FRIENDLY", 422), "invalid_request")


async def test_cup_rounds_and_repeated_pairing(client: httpx.AsyncClient) -> None:
    """matches spec: numbered cup rounds and a pairing played twice with the same home team."""
    fa_cup = await season_id(client, "FA Cup")
    round_1 = (await get(client, f"/v1/matches?season_id={fa_cup}&stage=ROUND"))["data"]
    assert [(m["matchday"], m["occurrence"], m["home_score"], m["away_score"]) for m in round_1] == [
        (1, 1, 1, 1),
        (1, 2, 2, 4),
    ]
    assert len({m["id"] for m in round_1}) == 2
    [semi] = (await get(client, f"/v1/matches?season_id={fa_cup}&stage=SF"))["data"]
    assert (semi["occurrence"], semi["decided_by"], semi["home_pens"], semi["away_pens"]) == (1, "PENALTIES", 2, 4)


async def test_seasons(client: httpx.AsyncClient) -> None:
    pl = await competition_id(client, "Premier League")
    [season] = (await get(client, f"/v1/seasons?competition_id={pl}"))["data"]
    assert (season["label"], season["competition_id"]) == ("2024-25", pl)
    assert season["coverage"] == {"scorers": "none", "players": "none"}
    assert await get(client, f"/v1/seasons/{season['id']}") == season

    wc = await get(client, f"/v1/seasons/{await season_id(client, 'FIFA World Cup')}")
    assert (wc["starts_on"], wc["status"], wc["coverage"]) == ("2022-11-20", "COMPLETED", {"scorers": "full", "players": "full"})


async def test_teams(client: httpx.AsyncClient) -> None:
    united = await find(client, "/v1/teams?expand=seasons", "Manchester United")
    assert (united["country"], united["kind"]) == ("GB-ENG", "CLUB")
    pl_season, fa_cup = await season_id(client, "Premier League"), await season_id(client, "FA Cup")
    assert sorted(s["season_id"] for s in united["seasons"]) == sorted([pl_season, fa_cup])

    by_id = await get(client, f"/v1/teams/{united['id']}")
    assert by_id["seasons"] is None
    assert (await get(client, f"/v1/teams/{united['id']}?expand=seasons"))["seasons"] == united["seasons"]

    euro = await season_id(client, "UEFA European Championship")
    nationals = await get(client, f"/v1/teams?season_id={euro}&kind=NATIONAL")
    assert [t["name"] for t in nationals["data"]] == ["England", "Spain"]

    euro_competition = await competition_id(client, "UEFA European Championship")
    assert (await get(client, f"/v1/teams?competition_id={euro_competition}"))["data"] == nationals["data"]


async def test_players_coverage(client: httpx.AsyncClient) -> None:
    united, pl = await team_id(client, "Manchester United"), await season_id(client, "Premier League")
    none = await get(client, f"/v1/players?team_id={united}&season_id={pl}")
    assert none == {"data": [], "next_cursor": None, "coverage": {"players": "none"}}

    spain, euro = await team_id(client, "Spain"), await season_id(client, "UEFA European Championship")
    squad = await get(client, f"/v1/players?team_id={spain}&season_id={euro}&limit=200")
    assert squad["coverage"] == {"players": "full"}
    assert len(squad["data"]) == 26
    assert all(p["nationality"] == "ES" for p in squad["data"])

    argentina, wc = await team_id(client, "Argentina"), await season_id(client, "FIFA World Cup")
    players = await get(client, f"/v1/players?team_id={argentina}&season_id={wc}&limit=200")
    messi = next(p for p in players["data"] if p["display_name"] == "Lionel Messi")
    assert (messi["given_name"], messi["family_name"], messi["dob"]) == ("Lionel", "Messi", "1987-06-24")
    assert await get(client, f"/v1/players/{messi['id']}") == messi


async def test_matches_filters(client: httpx.AsyncClient) -> None:
    pl_season = await season_id(client, "Premier League")
    pl = await get(client, f"/v1/matches?season_id={pl_season}&limit=200")
    assert len(pl["data"]) == 20
    assert pl["data"][0]["kickoff_utc"] == "2024-08-16T19:00:00Z"
    assert {m["competition_id"] for m in pl["data"]} == {await competition_id(client, "Premier League")}

    united = await team_id(client, "Manchester United")
    theirs = await get(client, f"/v1/matches?team_id={united}")
    assert len(theirs["data"]) == 4  # two Premier League, the FA Cup semi-final and final
    assert all(united in (m["home_team_id"], m["away_team_id"]) for m in theirs["data"])

    window = await get(client, "/v1/matches?from=2024-08-16&to=2024-08-16")
    assert [m["kickoff_utc"][:10] for m in window["data"]] == ["2024-08-16"]

    finals = await get(client, "/v1/matches?stage=FINAL&limit=200")
    assert len(finals["data"]) == 5


async def test_match_expand_and_penalties(client: httpx.AsyncClient) -> None:
    wc = await season_id(client, "FIFA World Cup")
    [final] = (await get(client, f"/v1/matches?season_id={wc}&stage=FINAL&expand=teams,venue,scorers"))["data"]
    assert (final["home_team"]["name"], final["away_team"]["name"]) == ("Argentina", "France")
    assert (final["home_score"], final["away_score"], final["decided_by"], final["home_pens"], final["away_pens"]) == (
        3, 3, "PENALTIES", 4, 2,
    )
    assert final["venue"]["name"] == "Lusail Stadium"
    assert final["coverage"] == {"scorers": "full"}
    assert [(g["name"], g["minute"], g["is_penalty"], g["side"]) for g in final["scorers"]] == [
        ("Lionel Messi", 23, True, "HOME"),
        ("Lionel Messi", 108, False, "HOME"),
        ("Angel Di Maria", 36, False, "HOME"),
        ("Kylian Mbappe", 80, True, "AWAY"),
        ("Kylian Mbappe", 81, False, "AWAY"),
        ("Kylian Mbappe", 118, True, "AWAY"),
    ]
    assert all(g["player"] for g in final["scorers"])

    plain = await get(client, f"/v1/matches/{final['id']}")
    assert plain["home_team"] is None and plain["scorers"] is None
    assert_error(await get(client, f"/v1/matches/{final['id']}?expand=lineups", 422), "invalid_expand")


async def test_partial_coverage_is_exposed_honestly(client: httpx.AsyncClient) -> None:
    pl_season = await season_id(client, "Premier League")
    [match] = (await get(client, f"/v1/matches?season_id={pl_season}&limit=1&expand=scorers"))["data"]
    assert match["scorers"] == []
    assert match["coverage"] == {"scorers": "none"}


async def test_venues(client: httpx.AsyncClient) -> None:
    venues = await get(client, "/v1/venues?limit=200")
    berlin = next(v for v in venues["data"] if v["city"] == "Berlin")
    assert berlin["name"] == "Olympiastadion"
    assert await get(client, f"/v1/venues/{berlin['id']}") == berlin
    assert_error(await get(client, f"/v1/venues/{UNKNOWN}", 404), "not_found")


async def test_openapi_documents_every_endpoint(client: httpx.AsyncClient) -> None:
    spec = await get(client, "/openapi.json")
    assert set(spec["paths"]) >= {
        "/v1/competitions", "/v1/competitions/{id}", "/v1/seasons", "/v1/seasons/{id}",
        "/v1/teams", "/v1/teams/{id}", "/v1/players", "/v1/players/{id}",
        "/v1/venues", "/v1/venues/{id}", "/v1/matches", "/v1/matches/{id}",
    }
    params = {p["name"] for p in spec["paths"]["/v1/matches"]["get"]["parameters"]}
    assert {"competition_id", "season_id", "team_id"} <= params
    assert "slug" not in str(spec).lower()
    assert "coverage" in spec["info"]["description"].lower()


async def test_verification_field_and_filter(client: httpx.AsyncClient) -> None:
    """match-verification spec: `verification` on matches and the `?verification=` filter."""
    pl_season = await season_id(client, "Premier League")
    first, second, *_ = (await get(client, f"/v1/matches?season_id={pl_season}&limit=3"))["data"]
    checked = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    async with get_sessionmaker()() as session, session.begin():
        for match, status in ((first, VerificationStatus.VERIFIED), (second, VerificationStatus.MISMATCH)):
            session.add(
                MatchVerification(
                    match_id=match["id"], reference=VerificationReference.WIKIPEDIA, status=status, checked_at=checked
                )
            )
    try:
        got = await get(client, f"/v1/matches/{first['id']}")
        assert got["verification"] == {"status": "VERIFIED", "reference": "wikipedia", "checked_at": "2026-10-10T12:00:00Z"}
        assert got["home_score"] == first["home_score"]

        mismatches = (await get(client, "/v1/matches?verification=MISMATCH&limit=200"))["data"]
        assert [m["id"] for m in mismatches] == [second["id"]]
        assert (await get(client, "/v1/matches?verification=SOURCE_BEHIND"))["data"] == []

        wc = await season_id(client, "FIFA World Cup")
        [final] = (await get(client, f"/v1/matches?season_id={wc}&stage=FINAL"))["data"]
        assert final["verification"] is None

        assert_error(await get(client, "/v1/matches?verification=MAYBE", 422), "invalid_request")
    finally:
        async with get_sessionmaker()() as session, session.begin():
            await session.execute(delete(MatchVerification))


async def test_openapi_lists_verification_statuses(client: httpx.AsyncClient) -> None:
    spec = await get(client, "/openapi.json")
    params = {p["name"]: p for p in spec["paths"]["/v1/matches"]["get"]["parameters"]}
    schema = params["verification"]["schema"]
    enum_ref = next(s["$ref"] for s in schema["anyOf"] if "$ref" in s).rsplit("/", 1)[-1]
    assert spec["components"]["schemas"][enum_ref]["enum"] == ["VERIFIED", "MISMATCH", "UNCONFIRMED", "SOURCE_BEHIND"]
    assert "verification" in spec["components"]["schemas"]["MatchOut"]["properties"]
