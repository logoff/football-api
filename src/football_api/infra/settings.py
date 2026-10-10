from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://football:football@127.0.0.1:5432/football"
    sources_dir: Path = Path(".cache/sources")
    wikidata_enabled: bool = True
    wikidata_endpoint: str = "https://query.wikidata.org/sparql"


@lru_cache
def get_settings() -> Settings:
    return Settings()
