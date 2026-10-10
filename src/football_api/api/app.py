from fastapi import FastAPI

from football_api.api import v1
from football_api.api.errors import install_error_handlers

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

**Coverage.** Goal scorers and squads exist only for FIFA World Cup 2022, UEFA Euro 2024,
Copa América 2024 and FIFA Club World Cup 2025; every other competition has results
only. Responses say so in a `coverage` field.
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="Football API",
        version="0.1.0",
        description=DESCRIPTION,
        openapi_tags=[
            {"name": "catalog", "description": "Competitions, seasons, teams, players, venues"},
            {"name": "matches", "description": "Fixtures, results and goal scorers"},
        ],
    )
    install_error_handlers(app)

    @app.get("/healthz", tags=["ops"], summary="Liveness check")
    async def healthz() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    app.include_router(v1.router)
    return app


app = create_app()
