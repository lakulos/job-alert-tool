from __future__ import annotations

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any

from bs4 import BeautifulSoup


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(BeautifulSoup(unescape(value), "html.parser").stripped_strings)


def parse_datetime(value: Any, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        # Lever uses epoch milliseconds; several other APIs use epoch seconds.
        timestamp = value / 1000 if value > 10_000_000_000 else value
        parsed = datetime.fromtimestamp(timestamp, tz=UTC)
    elif isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"\d{10}(?:\.\d+)?", text):
            parsed = datetime.fromtimestamp(float(text), tz=UTC)
        else:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                parsed = parsedate_to_datetime(text)
    elif fallback is not None:
        parsed = fallback
    else:
        raise ValueError("missing posting date")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def required(mapping: dict[str, Any], key: str) -> Any:
    value = mapping.get(key)
    if value is None or value == "":
        raise ValueError(f"missing required field {key}")
    return value
