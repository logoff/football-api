"""The committed `schema.graphql` matches the live schema, so every schema change shows in a diff (design D9)."""

from pathlib import Path

from football_api.api.graphql.schema import schema

SCHEMA_FILE = Path(__file__).parent.parent / "schema.graphql"


def test_committed_schema_is_current() -> None:
    assert SCHEMA_FILE.read_text() == schema.as_str() + "\n", "schema.graphql is out of date: run `just graphql-schema`"
