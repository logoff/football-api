"""One DataLoader per relation, per request (design D5): a batch of keys becomes one select."""

import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import TYPE_CHECKING

from strawberry.dataloader import DataLoader

from football_api.api import queries
from football_api.domain.enums import Side, VerificationAspect
from football_api.infra.models import (
    Card,
    Competition,
    Goal,
    LineupEntry,
    MatchVerification,
    Player,
    Season,
    Substitution,
    Team,
    Venue,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from football_api.api.graphql.context import Context


class Loaders:
    def __init__(self, ctx: "Context") -> None:
        def loader[K, V](
            fetch: "Callable[[AsyncSession, list[K]], Awaitable[Mapping[K, V]]]", default: Callable[[], V]
        ) -> DataLoader[K, V]:
            async def load(keys: Sequence[K]) -> list[V]:
                async with ctx.db() as session:
                    found = await fetch(session, list(keys))
                return [found[k] if k in found else default() for k in keys]

            return DataLoader(load_fn=load)

        def by_id[M: (Competition, Season, Team, Player, Venue)](model: type[M]) -> DataLoader[uuid.UUID, M | None]:
            return loader(lambda s, ids: queries.by_id(s, model, ids), lambda: None)

        self.competition = by_id(Competition)
        self.season = by_id(Season)
        self.team = by_id(Team)
        self.player = by_id(Player)
        self.venue = by_id(Venue)
        self.team_seasons: DataLoader[uuid.UUID, list[Season]] = loader(queries.team_seasons, list)
        self.verifications: DataLoader[uuid.UUID, dict[VerificationAspect, MatchVerification]] = loader(
            _verifications, dict
        )
        self.goals: DataLoader[uuid.UUID, list[tuple[Goal, str | None]]] = loader(queries.goals, list)
        self.lineups: DataLoader[uuid.UUID, dict[Side, list[LineupEntry]]] = loader(_lineups, dict)
        self.substitutions: DataLoader[uuid.UUID, list[Substitution]] = loader(queries.substitutions, list)
        self.cards: DataLoader[uuid.UUID, list[Card]] = loader(queries.cards, list)


async def _verifications(
    session: "AsyncSession", match_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[VerificationAspect, MatchVerification]]:
    out: dict[uuid.UUID, dict[VerificationAspect, MatchVerification]] = {}
    for (match_id, aspect), v in (await queries.verifications(session, match_ids)).items():
        out.setdefault(match_id, {})[aspect] = v
    return out


async def _lineups(session: "AsyncSession", match_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[Side, list[LineupEntry]]]:
    out: dict[uuid.UUID, dict[Side, list[LineupEntry]]] = {}
    for (match_id, side), entries in (await queries.lineup_entries(session, match_ids)).items():
        out.setdefault(match_id, {})[side] = entries
    return out
