"""Per-request context: one database session, used by one resolver at a time, and the loaders."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.fastapi import BaseContext

from football_api.infra.db import session_dependency


class Context(BaseContext):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session
        # Sibling fields resolve concurrently, and an AsyncSession allows one operation at a time.
        self._lock = asyncio.Lock()
        from football_api.api.graphql.loaders import Loaders

        self.loaders = Loaders(self)

    @asynccontextmanager
    async def db(self) -> AsyncGenerator[AsyncSession]:
        async with self._lock:
            yield self._session


async def get_context(session: Annotated[AsyncSession, Depends(session_dependency)]) -> Context:
    return Context(session)
