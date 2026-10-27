from fastapi import FastAPI

from football_api.api import v1
from football_api.api.errors import install_error_handlers
from football_api.api.graphql.schema import graphql_router

DESCRIPTION = """
Football (soccer) statistics from public-domain [openfootball](https://github.com/openfootball)
data, with Wikidata identifiers.

**Conventions**

- Every identifier is a UUID, in paths and in filters (`season_id`, `team_id`, …).
  List a resource to find IDs by name.
- Lists are cursor-paginated: pass a page's `next_cursor` as `cursor`.
- Related resources are embedded on request with `expand=…`.
- Timestamps are UTC (`Z`).
- Errors use `{"error": {"code", "message", "details"}}`.

**Coverage.** Goal scorers, squads, line-ups, substitutions and cards exist only for some
competitions and seasons; every season and match says which in a `coverage` field. Line-ups,
substitutions and cards (`expand=lineups,substitutions,cards`) cover every FIFA World Cup and
FIFA Club World Cup, and the 2025-26 Premier League, La Liga, Bundesliga, Serie A and Ligue 1.
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="Football API",
        version="0.1.0",
        description=DESCRIPTION,
        openapi_tags=[
            {"name": "catalog", "description": "Competitions, seasons, teams, players, venues"},
            {"name": "matches", "description": "Fixtures, results, goal scorers, line-ups and cards"},
        ],
    )
    install_error_handlers(app)

    @app.get("/healthz", tags=["ops"], summary="Liveness check")
    async def healthz() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    app.include_router(v1.router)
    app.include_router(graphql_router(), prefix="/graphql", include_in_schema=False)
    return app


app = create_app()
