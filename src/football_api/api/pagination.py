"""Keyset pagination with opaque cursors.

A cursor is base64url(JSON) of the last row's sort-key values. The next page selects
rows whose `(sort columns…, id)` tuple sorts after it, so pages stay stable while
data is inserted, and no OFFSET scans are needed.
"""

import base64
import binascii
import json
import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Annotated, Any, cast

from fastapi import Query
from sqlalchemy import Select, tuple_
from sqlalchemy.orm import InstrumentedAttribute

from football_api.api.errors import ApiError

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Page size")]
Cursor = Annotated[str | None, Query(description="Opaque cursor from a previous page's `next_cursor`")]


def _encode_value(value: object) -> object:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _decode_value(raw: object, column: InstrumentedAttribute[Any]) -> object:
    python_type: type = column.type.python_type
    if raw is None:
        return None
    if python_type is datetime:
        return datetime.fromisoformat(str(raw))
    if python_type is date:
        return date.fromisoformat(str(raw))
    if python_type is uuid.UUID:
        return uuid.UUID(str(raw))
    return raw


def encode_cursor(values: Sequence[object]) -> str:
    payload = json.dumps([_encode_value(v) for v in values], separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str, columns: Sequence[InstrumentedAttribute[Any]]) -> list[object]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw: object = json.loads(base64.urlsafe_b64decode(padded))
        if not isinstance(raw, list):
            raise ValueError("cursor shape")
        values = cast(list[object], raw)
        if len(values) != len(columns):
            raise ValueError("cursor shape")
        return [_decode_value(v, c) for v, c in zip(values, columns, strict=True)]
    except (ValueError, binascii.Error, json.JSONDecodeError) as exc:
        raise ApiError(422, "invalid_cursor", "Cursor is malformed or from another listing") from exc


def apply_keyset[*Ts](
    stmt: Select[*Ts], columns: Sequence[InstrumentedAttribute[Any]], limit: int, cursor: str | None
) -> Select[*Ts]:
    if cursor:
        after = decode_cursor(cursor, columns)
        stmt = stmt.where(tuple_(*columns) > tuple_(*after))
    return stmt.order_by(*columns).limit(limit + 1)

