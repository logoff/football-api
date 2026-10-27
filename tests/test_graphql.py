"""GraphQL endpoint against the fixture-synced database (graphql-api spec).

Parity tests run the same request through REST and GraphQL and compare the values, with REST's
snake_case keys turned into GraphQL's camelCase.
"""

import re
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, cast

import httpx
import pytest
from sqlalchemy import delete, event
from test_api import competition_id, get, season_id

from football_api.domain.enums import Stage, VerificationAspect, VerificationReference, VerificationStatus
from football_api.infra.db import get_engine, get_sessionmaker
from football_api.infra.models import MatchVerification, StandingVerification

pytestmark = pytest.mark.db

UNKNOWN = "00000000-0000-7000-8000-000000000000"


async def gql(
    client: httpx.AsyncClient, query: str, variables: dict[str, Any] | None = None, *, errors: bool = False
) -> dict[str, Any]:
    """POST a query; without `errors`, fail on any error and return `data`, else return the whole body."""
    resp = await client.post("/graphql", json={"query": query, "variables": variables or {}})
    body = cast(dict[str, Any], resp.json())
    if errors:
        return body
    assert resp.status_code == 200 and "errors" not in body, body
    return cast(dict[str, Any], body["data"])


def camel(value: Any) -> Any:
    """REST JSON with camelCase keys, as GraphQL names its fields."""
    if isinstance(value, dict):
        items = cast(dict[str, Any], value).items()
        return {re.sub(r"_([a-z])", lambda m: m.group(1).upper(), k): camel(v) for k, v in items}
    if isinstance(value, list):
        return [camel(v) for v in cast(list[Any], value)]
    return value


def nodes(connection: dict[str, Any]) -> list[dict[str, Any]]:
    return [e["node"] for e in connection["edges"]]


def codes(body: dict[str, Any]) -> list[str]:
    return [e["extensions"]["code"] for e in body.get("errors", [])]


# --- endpoint (2.1) ----------------------------------------------------------------


async def test_query_by_post_and_get(client: httpx.AsyncClient) -> None:
    query = "{ competitions(first: 2) { edges { node { name } } } }"
    posted = await gql(client, query)
    assert len(posted["competitions"]["edges"]) == 2

    resp = await client.get("/graphql", params={"query": query})
    assert resp.status_code == 200
    assert resp.json()["data"] == posted


async def test_mutation_refused(client: httpx.AsyncClient) -> None:
    body = await gql(client, "mutation { competitions { edges { cursor } } }", errors=True)
    assert body["errors"] and not body.get("data")


async def test_browser_gets_the_explorer(client: httpx.AsyncClient) -> None:
    resp = await client.get("/graphql", headers={"Accept": "text/html"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "graphiql" in resp.text.lower()


async def test_rest_openapi_leaves_graphql_out(client: httpx.AsyncClient) -> None:
    assert not any(p.startswith("/graphql") for p in (await get(client, "/openapi.json"))["paths"])


# --- connections (2.2) -------------------------------------------------------------


async def all_match_ids(client: httpx.AsyncClient) -> list[str]:
    ids: list[str] = []
    cursor = ""
    while True:
        page = await get(client, f"/v1/matches?limit=200{'&cursor=' + cursor if cursor else ''}")
        ids += [m["id"] for m in page["data"]]
        if not page["next_cursor"]:
            return ids
        cursor = page["next_cursor"]


async def test_connection_default_and_maximum_page(client: httpx.AsyncClient) -> None:
    total = len(await all_match_ids(client))
    assert total > 50  # the fixtures hold enough matches to need a second default page
    data = await gql(client, "{ matches { edges { cursor } pageInfo { hasNextPage } } }")
    assert len(data["matches"]["edges"]) == 50 and data["matches"]["pageInfo"]["hasNextPage"]
    data = await gql(client, "{ matches(first: 200) { edges { cursor } pageInfo { hasNextPage } } }")
    assert len(data["matches"]["edges"]) == min(total, 200)
    assert data["matches"]["pageInfo"]["hasNextPage"] == (total > 200)


async def test_connection_pages_once_through_everything(client: httpx.AsyncClient) -> None:
    rest_ids = await all_match_ids(client)
    size = len(rest_ids) // 2 + 1  # two pages, the second shorter
    query = """query($n: Int!, $after: String) {
      matches(first: $n, after: $after) { edges { node { id } } pageInfo { hasNextPage endCursor } }
    }"""
    first = (await gql(client, query, {"n": size}))["matches"]
    second = (await gql(client, query, {"n": size, "after": first["pageInfo"]["endCursor"]}))["matches"]
    assert first["pageInfo"]["hasNextPage"] and not second["pageInfo"]["hasNextPage"]
    # Every match once, in REST's order, and the same cursor REST hands out
    assert [n["id"] for n in nodes(first) + nodes(second)] == rest_ids
    rest = await get(client, f"/v1/matches?limit={size}")
    assert rest["next_cursor"] == first["pageInfo"]["endCursor"]


async def test_connection_page_too_large(client: httpx.AsyncClient) -> None:
    body = await gql(client, "{ competitions(first: 500) { edges { cursor } } }", errors=True)
    assert codes(body) == ["page_too_large"]


async def test_connection_bad_cursor(client: httpx.AsyncClient) -> None:
    body = await gql(client, '{ competitions(after: "not-a-cursor") { edges { cursor } } }', errors=True)
    assert codes(body) == ["invalid_cursor"]
    assert body["errors"][0]["path"] == ["competitions"]


async def test_error_in_one_field_keeps_the_rest(client: httpx.AsyncClient) -> None:
    body = await gql(
        client,
        '{ bad: competitions(after: "not-a-cursor") { edges { cursor } } good: competitions(first: 1) { edges { cursor } } }',
        errors=True,
    )
    assert codes(body) == ["invalid_cursor"]
    assert len(body["data"]["good"]["edges"]) == 1


async def test_unknown_lookup_is_null(client: httpx.AsyncClient) -> None:
    data = await gql(
        client,
        "query($id: UUID!) { competition(id: $id) { name } season(id: $id) { label } team(id: $id) { name } "
        "player(id: $id) { displayName } venue(id: $id) { name } match(id: $id) { id } }",
        {"id": UNKNOWN},
    )
    assert set(data.values()) == {None}


# --- catalog parity (2.3) ----------------------------------------------------------

COMPETITION = "id name country teamKind scope format"
COVERAGE = "coverage { scorers players lineups substitutions cards }"
SEASON = f"id competitionId label startsOn endsOn status {COVERAGE}"
TEAM = "id name country kind"
PLAYER = "id displayName fullName givenName familyName birthYear dob nationality position"
VENUE = "id name city country"


async def test_competitions_parity(client: httpx.AsyncClient) -> None:
    expected: list[dict[str, Any]] = []
    for rest, args in (("", ""), ("&format=CUP", "format: CUP")):
        expected = camel((await get(client, f"/v1/competitions?limit=200{rest}"))["data"])
        data = await gql(client, f"{{ competitions(first: 200 {args}) {{ edges {{ node {{ {COMPETITION} }} }} }} }}")
        assert nodes(data["competitions"]) == expected and expected
    one = expected[0]
    assert (await gql(client, f'{{ competition(id: "{one["id"]}") {{ {COMPETITION} }} }}'))["competition"] == one


async def test_seasons_parity(client: httpx.AsyncClient) -> None:
    wc = await competition_id(client, "FIFA World Cup")
    expected: list[dict[str, Any]] = []
    for rest, args in (("", ""), (f"&competition_id={wc}", f'competitionId: "{wc}"')):
        expected = camel((await get(client, f"/v1/seasons?limit=200{rest}"))["data"])
        data = await gql(client, f"{{ seasons(first: 200 {args}) {{ edges {{ node {{ {SEASON} }} }} }} }}")
        assert nodes(data["seasons"]) == expected and expected
    [season] = expected
    assert season["coverage"]["lineups"] == "full"
    assert (await gql(client, f'{{ season(id: "{season["id"]}") {{ {SEASON} }} }}'))["season"] == season


def team_with_seasons(rest_team: dict[str, Any]) -> dict[str, Any]:
    """REST `expand=seasons` lists season IDs; GraphQL links the seasons themselves."""
    seasons = [{"id": s["season_id"], "competitionId": s["competition_id"], "label": s["label"]} for s in rest_team["seasons"]]
    return {**camel({k: v for k, v in rest_team.items() if k != "seasons"}), "seasons": seasons}


async def find_team(client: httpx.AsyncClient, name: str) -> dict[str, Any]:
    teams = cast(list[dict[str, Any]], (await get(client, "/v1/teams?limit=200&expand=seasons"))["data"])
    return next(t for t in teams if t["name"] == name)


async def test_teams_parity(client: httpx.AsyncClient) -> None:
    euro_competition = await competition_id(client, "UEFA European Championship")
    euro = await season_id(client, "UEFA European Championship")
    filters = (
        ("", ""),
        ("&kind=NATIONAL", "kind: NATIONAL"),
        (f"&competition_id={euro_competition}", f'competitionId: "{euro_competition}"'),
        (f"&season_id={euro}&kind=NATIONAL", f'seasonId: "{euro}", kind: NATIONAL'),
    )
    for rest, args in filters:
        expected = [team_with_seasons(t) for t in (await get(client, f"/v1/teams?limit=200&expand=seasons{rest}"))["data"]]
        query = f"{{ teams(first: 200 {args}) {{ edges {{ node {{ {TEAM} seasons {{ id competitionId label }} }} }} }} }}"
        assert nodes((await gql(client, query))["teams"]) == expected and expected
    united = await find_team(client, "Manchester United")
    data = await gql(client, f'{{ team(id: "{united["id"]}") {{ {TEAM} seasons {{ id competitionId label }} }} }}')
    assert data["team"] == team_with_seasons(united)


async def test_players_parity(client: httpx.AsyncClient) -> None:
    spain, euro = (await find_team(client, "Spain"))["id"], await season_id(client, "UEFA European Championship")
    united, pl = (await find_team(client, "Manchester United"))["id"], await season_id(client, "Premier League")
    wc = await competition_id(client, "FIFA World Cup")
    filters = (
        (f"&team_id={spain}&season_id={euro}", f'teamId: "{spain}", seasonId: "{euro}"'),
        (f"&team_id={united}&season_id={pl}", f'teamId: "{united}", seasonId: "{pl}"'),
        (f"&competition_id={wc}", f'competitionId: "{wc}"'),
        ("", ""),
    )
    for rest, args in filters:
        page = await get(client, f"/v1/players?limit=200{rest}")
        data = await gql(client, f"{{ players(first: 200 {args}) {{ coverage {{ players }} edges {{ node {{ {PLAYER} }} }} }} }}")
        assert nodes(data["players"]) == camel(page["data"])
        assert data["players"]["coverage"] == page.get("coverage")
    query = f'{{ team(id: "{spain}") {{ players(seasonId: "{euro}", first: 200) {{ coverage {{ players }} edges {{ node {{ id }} }} }} }} }}'
    squad = (await gql(client, query))["team"]["players"]
    assert squad["coverage"] == {"players": "full"} and len(squad["edges"]) == 26
    one = camel((await get(client, f"/v1/players?team_id={spain}&season_id={euro}"))["data"][0])
    assert (await gql(client, f'{{ player(id: "{one["id"]}") {{ {PLAYER} }} }}'))["player"] == one


async def test_venues_parity(client: httpx.AsyncClient) -> None:
    expected = camel((await get(client, "/v1/venues?limit=200"))["data"])
    data = await gql(client, f"{{ venues(first: 200) {{ edges {{ node {{ {VENUE} }} }} }} }}")
    assert nodes(data["venues"]) == expected and expected
    assert (await gql(client, f'{{ venue(id: "{expected[0]["id"]}") {{ {VENUE} }} }}'))["venue"] == expected[0]


# --- matches parity (2.4) ----------------------------------------------------------

REF = "{ id displayName }"
VERIFICATION = "{ status reference checkedAt }"
LINEUP = f"{{ formation entries {{ player {REF} name role line isCaptain }} }}"
MATCH = f"""
  id competitionId seasonId stage matchday occurrence roundLabel kickoffUtc originalKickoffUtc status
  homeTeamId awayTeamId venueId homeScore awayScore decidedBy homePens awayPens awarded referee attendance
  coverage {{ scorers lineups substitutions cards }}
  verification {VERIFICATION} eventsVerification {VERIFICATION}
  homeTeam {{ {TEAM} }} awayTeam {{ {TEAM} }} venue {{ {VENUE} }}
  scorers {{ ordinal side player {REF} name minute addedMinute isPenalty isOwnGoal }}
  lineups {{ home {LINEUP} away {LINEUP} }}
  substitutions {{ side minute addedMinute playerOff {REF} playerOffName playerOn {REF} playerOnName }}
  cards {{ side minute addedMinute kind player {REF} name }}
"""
EVERY_EXPAND = "expand=teams,venue,scorers,lineups,substitutions,cards"


def rest_match(m: dict[str, Any]) -> dict[str, Any]:
    """A REST match with every expand, as GraphQL serves it: teams carry no `seasons` (null in REST)."""
    out = camel(m)
    for side in ("homeTeam", "awayTeam"):
        if out[side] is not None:
            del out[side]["seasons"]
    return cast(dict[str, Any], out)


async def assert_matches_parity(client: httpx.AsyncClient, rest: str, args: str) -> list[dict[str, Any]]:
    expected = [rest_match(m) for m in (await get(client, f"/v1/matches?limit=200&{EVERY_EXPAND}{rest}"))["data"]]
    data = await gql(client, f"{{ matches(first: 200 {args}) {{ edges {{ node {{ {MATCH} }} }} }} }}")
    assert nodes(data["matches"]) == expected
    return expected


async def test_matches_parity_for_every_filter(client: httpx.AsyncClient) -> None:
    pl_competition, pl = await competition_id(client, "Premier League"), await season_id(client, "Premier League")
    united = (await find_team(client, "Manchester United"))["id"]
    filters = (
        ("", ""),
        (f"&competition_id={pl_competition}", f'competitionId: "{pl_competition}"'),
        (f"&season_id={pl}", f'seasonId: "{pl}"'),
        (f"&team_id={united}", f'teamId: "{united}"'),
        ("&stage=FINAL", "stage: FINAL"),
        ("&from=2024-08-16&to=2024-08-17", 'from: "2024-08-16", to: "2024-08-17"'),
    )
    for rest, args in filters:
        assert await assert_matches_parity(client, rest, args)


async def test_match_parity_with_and_without_events(client: httpx.AsyncClient) -> None:
    cwc, pl = await season_id(client, "FIFA Club World Cup"), await season_id(client, "Premier League")
    [final] = (await get(client, f"/v1/matches?season_id={cwc}&stage=FINAL&{EVERY_EXPAND}"))["data"]
    [plain] = (await get(client, f"/v1/matches?season_id={pl}&limit=1&{EVERY_EXPAND}"))["data"]
    for rest in (final, plain):
        expected = rest_match(await get(client, f"/v1/matches/{rest['id']}?{EVERY_EXPAND}"))
        assert (await gql(client, f'{{ match(id: "{rest["id"]}") {{ {MATCH} }} }}'))["match"] == expected
    assert final["lineups"]["home"]["formation"] == "5-3-2" and final["cards"]
    assert rest_match(plain)["coverage"]["lineups"] == "none" and plain["lineups"]["home"]["entries"] == []


async def test_verification_parity(client: httpx.AsyncClient) -> None:
    pl = await season_id(client, "Premier League")
    first, second, *_ = (await get(client, f"/v1/matches?season_id={pl}&limit=3"))["data"]
    checked = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    rows = (
        (first, VerificationAspect.RESULT, VerificationStatus.VERIFIED),
        (second, VerificationAspect.RESULT, VerificationStatus.MISMATCH),
        (first, VerificationAspect.EVENTS, VerificationStatus.MISMATCH),
    )
    async with get_sessionmaker()() as session, session.begin():
        for match, aspect, status in rows:
            session.add(
                MatchVerification(
                    match_id=match["id"], reference=VerificationReference.WIKIPEDIA, aspect=aspect, status=status, checked_at=checked
                )
            )
    try:
        for rest, args in (
            ("&verification=MISMATCH", "verification: MISMATCH"),
            ("&verification=VERIFIED", "verification: VERIFIED"),
            ("&events_verification=MISMATCH", "eventsVerification: MISMATCH"),
            ("&verification=SOURCE_BEHIND", "verification: SOURCE_BEHIND"),
        ):
            await assert_matches_parity(client, rest, args)
        got = (await gql(client, f'{{ match(id: "{first["id"]}") {{ verification {VERIFICATION} }} }}'))["match"]
        assert got["verification"] == {"status": "VERIFIED", "reference": "wikipedia", "checkedAt": "2026-10-10T12:00:00Z"}
    finally:
        async with get_sessionmaker()() as session, session.begin():
            await session.execute(delete(MatchVerification))


# --- standings parity (2.5) --------------------------------------------------------

STANDINGS = f"""seasonId asOf tables {{ stage phase group status rows {{
  position teamId team {{ {TEAM} }} played won drawn lost goalsFor goalsAgainst goalDifference points
  adjustments {{ points reason source }} tied verification {VERIFICATION}
}} }}"""


def rest_standings(body: dict[str, Any]) -> dict[str, Any]:
    out = camel(body)
    for table in out["tables"]:
        for row in table["rows"]:
            del row["team"]["seasons"]
    return cast(dict[str, Any], out)


async def assert_standings_parity(client: httpx.AsyncClient, sid: str, as_of: str | None) -> dict[str, Any]:
    expected = rest_standings(await get(client, f"/v1/seasons/{sid}/standings?expand=teams{f'&as_of={as_of}' if as_of else ''}"))
    args = f'(asOf: "{as_of}")' if as_of else ""
    data = await gql(client, f'{{ season(id: "{sid}") {{ standings{args} {{ {STANDINGS} }} }} }}')
    assert data["season"]["standings"] == expected
    return expected


async def test_standings_parity(client: httpx.AsyncClient, fixture_seeds: None) -> None:
    seasons = (await get(client, "/v1/seasons?limit=200"))["data"]
    for season in seasons:
        await assert_standings_parity(client, season["id"], None)
    pl = await season_id(client, "Premier League")
    dated = await assert_standings_parity(client, pl, "2024-08-20")
    assert dated["tables"][0]["status"] == "provisional"
    full = await assert_standings_parity(client, pl, None)
    assert any(r["adjustments"] for r in full["tables"][0]["rows"])


async def test_standings_row_verification_parity(client: httpx.AsyncClient, fixture_seeds: None) -> None:
    sid = await season_id(client, "FIFA World Cup")
    netherlands = (await find_team(client, "Netherlands"))["id"]
    async with get_sessionmaker()() as session, session.begin():
        session.add(
            StandingVerification(
                season_id=uuid.UUID(sid),
                team_id=uuid.UUID(netherlands),
                stage=Stage.GROUP,
                phase=1,
                group_name="A",
                reference=VerificationReference.WIKIPEDIA,
                status=VerificationStatus.VERIFIED,
                checked_at=datetime(2031, 1, 1, tzinfo=UTC),
            )
        )
    try:
        final = await assert_standings_parity(client, sid, None)
        assert any(r["verification"] for r in final["tables"][0]["rows"])
        await assert_standings_parity(client, sid, "2022-12-31")
    finally:
        async with get_sessionmaker()() as session, session.begin():
            await session.execute(delete(StandingVerification))


# --- graph links (2.6) -------------------------------------------------------------


async def test_walk_from_a_competition_to_the_cards(client: httpx.AsyncClient) -> None:
    cwc = await competition_id(client, "FIFA Club World Cup")
    query = f"""{{ competition(id: "{cwc}") {{ {COMPETITION}
      seasons(first: 1) {{ edges {{ node {{ id
        competition {{ id }}
        teams(first: 200) {{ edges {{ node {{ id }} }} }}
        matches(first: 200, stage: FINAL) {{ edges {{ node {{ id
          season {{ id label }} competition {{ name }}
          homeTeam {{ name }} cards {{ kind player {REF} }}
        }} }} }}
      }} }} }}
    }} }}"""
    comp = (await gql(client, query))["competition"]
    expected = camel(await get(client, f"/v1/competitions/{cwc}"))
    assert {k: comp[k] for k in expected} == expected

    [season] = nodes(comp["seasons"])
    assert season["competition"] == {"id": cwc}
    rest_teams = (await get(client, f"/v1/teams?season_id={season['id']}&limit=200"))["data"]
    assert [t["id"] for t in nodes(season["teams"])] == [t["id"] for t in rest_teams]

    [final] = nodes(season["matches"])
    rest = await get(client, f"/v1/matches/{final['id']}?expand=teams,cards")
    assert final["season"]["id"] == rest["season_id"] and final["competition"]["name"] == "FIFA Club World Cup"
    assert final["homeTeam"]["name"] == rest["home_team"]["name"] == "Chelsea"
    assert final["cards"] == [{"kind": c["kind"], "player": camel(c["player"])} for c in rest["cards"]]


async def test_season_matches_take_the_rest_filters(client: httpx.AsyncClient) -> None:
    wc = await season_id(client, "FIFA World Cup")
    argentina = (await find_team(client, "Argentina"))["id"]
    rest = (await get(client, f"/v1/matches?season_id={wc}&team_id={argentina}&stage=FINAL"))["data"]
    query = f'{{ season(id: "{wc}") {{ matches(teamId: "{argentina}", stage: FINAL) {{ edges {{ node {{ id }} }} }} }} }}'
    assert [n["id"] for n in nodes((await gql(client, query))["season"]["matches"])] == [m["id"] for m in rest] and rest


# --- batching (2.7) ----------------------------------------------------------------


@contextmanager
def count_statements() -> Generator[list[str]]:
    statements: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        statements.append(statement)

    engine = get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


async def test_relations_are_batched(client: httpx.AsyncClient) -> None:
    query = f"query($n: Int!) {{ matches(first: $n) {{ edges {{ node {{ {MATCH} season {{ label }} competition {{ name }} }} }} }} }}"
    counts: list[int] = []
    for n in (2, 200):
        with count_statements() as statements:
            data = await gql(client, query, {"n": n})
        assert len(data["matches"]["edges"]) == min(n, len(await all_match_ids(client)))
        counts.append(len(statements))
    assert counts[0] == counts[1], counts


