from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://football:football@127.0.0.1:5432/football"
    seeds_dir: Path = Path("seeds")
    sources_dir: Path = Path(".cache/sources")
    alembic_ini: Path = Path("alembic.ini")
    wikidata_enabled: bool = True
    wikidata_endpoint: str = "https://query.wikidata.org/sparql"
    wikipedia_enabled: bool = True
    wikipedia_rest: str = "https://en.wikipedia.org/api/rest_v1"
    wikipedia_api: str = "https://en.wikipedia.org/w/api.php"


@lru_cache
def get_settings() -> Settings:
    return Settings()
