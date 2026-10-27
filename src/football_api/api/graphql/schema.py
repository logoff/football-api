"""The `Query` root, the schema and the `/graphql` router (design D1, D7, D8)."""

import logging
import uuid
from datetime import date, datetime
from typing import Annotated, Any

import strawberry
from graphql import GraphQLError
from starlette.requests import Request
from strawberry.fastapi import GraphQLRouter
from strawberry.http import GraphQLHTTPResponse
from strawberry.schema.config import StrawberryConfig
from strawberry.types import ExecutionContext, ExecutionResult

from football_api.api import queries
from football_api.api.errors import ApiError
from football_api.api.graphql.connection import Connection, connection, page_size
from football_api.api.graphql.limits import QueryLimitsExtension
from football_api.api.graphql.context import Context, get_context
from football_api.api.graphql.types import (
    UTC_DATETIME,
    Competition,
    GInfo,
    Match,
    Player,
    PlayerConnection,
    Season,
    Team,
    Venue,
    _players,  # pyright: ignore[reportPrivateUsage]
)
from football_api.domain.enums import CompetitionFormat, Stage, TeamKind, VerificationStatus

log = logging.getLogger(__name__)


@strawberry.type
class Query:
    @strawberry.field
    async def competition(self, info: GInfo, id: uuid.UUID) -> Competition | None:
        c = await info.context.loaders.competition.load(id)
        return Competition.of(c) if c else None

    @strawberry.field
    async def competitions(
        self, info: GInfo, format: CompetitionFormat | None = None, first: int | None = None, after: str | None = None
    ) -> Connection[Competition] | None:
        async with info.context.db() as s:
            listing = await queries.competitions(s, format=format, limit=page_size(first), cursor=after)
        return connection(listing, Competition.of)

    @strawberry.field
    async def season(self, info: GInfo, id: uuid.UUID) -> Season | None:
        s = await info.context.loaders.season.load(id)
        return Season.of(s) if s else None

    @strawberry.field
    async def seasons(
        self, info: GInfo, competition_id: uuid.UUID | None = None, first: int | None = None, after: str | None = None
    ) -> Connection[Season] | None:
        async with info.context.db() as s:
            listing = await queries.seasons(s, competition_id=competition_id, limit=page_size(first), cursor=after)
        return connection(listing, Season.of)

    @strawberry.field
    async def team(self, info: GInfo, id: uuid.UUID) -> Team | None:
        t = await info.context.loaders.team.load(id)
        return Team.of(t) if t else None

    @strawberry.field
    async def teams(
        self,
        info: GInfo,
        competition_id: uuid.UUID | None = None,
        season_id: uuid.UUID | None = None,
        kind: TeamKind | None = None,
        first: int | None = None,
        after: str | None = None,
    ) -> Connection[Team] | None:
        async with info.context.db() as s:
            listing = await queries.teams(
                s, competition_id=competition_id, season_id=season_id, kind=kind, limit=page_size(first), cursor=after
            )
        return connection(listing, Team.of)

    @strawberry.field
    async def player(self, info: GInfo, id: uuid.UUID) -> Player | None:
        p = await info.context.loaders.player.load(id)
        return Player.of(p) if p else None

    @strawberry.field(description="Players exist only where the source publishes squads; see `coverage`")
    async def players(
        self,
        info: GInfo,
        team_id: uuid.UUID | None = None,
        season_id: uuid.UUID | None = None,
        competition_id: uuid.UUID | None = None,
        first: int | None = None,
        after: str | None = None,
    ) -> PlayerConnection | None:
        return await _players(
            info, team_id=team_id, season_id=season_id, competition_id=competition_id, first=first, after=after
        )

    @strawberry.field
    async def venue(self, info: GInfo, id: uuid.UUID) -> Venue | None:
        v = await info.context.loaders.venue.load(id)
        return Venue.of(v) if v else None

    @strawberry.field
    async def venues(self, info: GInfo, first: int | None = None, after: str | None = None) -> Connection[Venue] | None:
        async with info.context.db() as s:
            listing = await queries.venues(s, limit=page_size(first), cursor=after)
        return connection(listing, Venue.of)

    @strawberry.field
    async def match(self, info: GInfo, id: uuid.UUID) -> Match | None:
        async with info.context.db() as s:
            row = await queries.match(s, id)
        return Match.of(row) if row else None

    @strawberry.field
    async def matches(
        self,
        info: GInfo,
        competition_id: uuid.UUID | None = None,
        season_id: uuid.UUID | None = None,
        team_id: uuid.UUID | None = None,
        stage: Stage | None = None,
        from_: Annotated[date | None, strawberry.argument(name="from", description="Kickoff on or after this UTC date")] = None,
        to: Annotated[date | None, strawberry.argument(description="Kickoff on or before this UTC date")] = None,
        verification: VerificationStatus | None = None,
        events_verification: VerificationStatus | None = None,
        first: int | None = None,
        after: str | None = None,
    ) -> Connection[Match] | None:
        async with info.context.db() as s:
            listing = await queries.matches(
                s,
                competition_id=competition_id,
                season_id=season_id,
                team_id=team_id,
                stage=stage,
                from_=from_,
                to=to,
                verification=verification,
                events_verification=events_verification,
                limit=page_size(first),
                cursor=after,
            )
        return connection(listing, Match.of)


def _coded(error: GraphQLError) -> GraphQLError:
    """Every error gets `extensions.code`: REST's code for an `ApiError`, `internal_error` for anything unexpected."""
    original = error.original_error
    if isinstance(original, ApiError):
        extensions: dict[str, Any] = {"code": original.code, **original.details}
        message = original.message
    elif original is None or isinstance(original, GraphQLError):
        extensions = {"code": "invalid_request", **(error.extensions or {})}
        message = error.message
    else:
        extensions, message = {"code": "internal_error"}, "Internal server error"
    return GraphQLError(message, nodes=error.nodes, source=error.source, positions=error.positions, path=error.path, extensions=extensions)


def _expected(error: GraphQLError) -> bool:
    return error.original_error is None or isinstance(error.original_error, ApiError | GraphQLError)


class FootballSchema(strawberry.Schema):
    def process_errors(self, errors: list[GraphQLError], execution_context: ExecutionContext | None = None) -> None:
        for error in errors:
            if not _expected(error):
                log.error("graphql resolver failed at %s", error.path, exc_info=error.original_error)


schema = FootballSchema(
    query=Query, config=StrawberryConfig(scalar_map={datetime: UTC_DATETIME}), extensions=[QueryLimitsExtension]
)


class Router(GraphQLRouter[Context, None]):
    async def process_result(self, request: Request, result: ExecutionResult) -> GraphQLHTTPResponse:
        response: GraphQLHTTPResponse = {"data": result.data}
        if result.errors:
            response["errors"] = [_coded(e).formatted for e in result.errors]
        if result.extensions:
            response["extensions"] = result.extensions
        return response


def graphql_router() -> GraphQLRouter[Context, None]:
    return Router(schema, context_getter=get_context, graphql_ide="graphiql", allow_queries_via_get=True)
