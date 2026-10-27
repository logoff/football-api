"""Relay-style connections over the REST keyset cursors (design D4). IDs stay plain UUIDs."""

from collections.abc import Callable
from typing import Generic, TypeVar

import strawberry
from graphql import GraphQLError

from football_api.api.pagination import DEFAULT_LIMIT, MAX_LIMIT
from football_api.api.queries import Listing

T = TypeVar("T")


@strawberry.type
class PageInfo:
    has_next_page: bool
    end_cursor: str | None = strawberry.field(description="Pass as `after` to get the next page")


@strawberry.type
class Edge(Generic[T]):
    cursor: str
    node: T


@strawberry.type
class Connection(Generic[T]):
    edges: list[Edge[T]]
    page_info: PageInfo


def edges_of[R, N](listing: Listing[R], build: Callable[[R], N]) -> tuple[list[Edge[N]], PageInfo]:
    """A listing's rows as edges, each node built with `build(row)`, and its page info."""
    edges = [Edge(cursor=c, node=build(row)) for row, c in zip(listing.items, listing.cursors, strict=True)]
    info = PageInfo(has_next_page=listing.next_cursor is not None, end_cursor=listing.cursors[-1] if listing.cursors else None)
    return edges, info


def connection[R, N](listing: Listing[R], build: Callable[[R], N]) -> Connection[N]:
    edges, info = edges_of(listing, build)
    return Connection(edges=edges, page_info=info)


def page_size(first: int | None) -> int:
    """`first`, or the REST default. Validation refuses a larger one before running; this guards resolvers."""
    if first is None:
        return DEFAULT_LIMIT
    if first > MAX_LIMIT:
        raise GraphQLError(
            f"`first` is at most {MAX_LIMIT}", extensions={"code": "page_too_large", "measured": first, "limit": MAX_LIMIT}
        )
    if first < 1:
        raise GraphQLError("`first` must be at least 1", extensions={"code": "invalid_request"})
    return first
