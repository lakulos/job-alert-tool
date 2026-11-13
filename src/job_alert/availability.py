from __future__ import annotations

import ipaddress
import logging
import queue
import socket
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from job_alert.http import HttpClient
from job_alert.models import Job
from job_alert.sources.common import parse_datetime

LOGGER = logging.getLogger(__name__)
_DEAD_STATUSES = {404, 410}
_GET_FALLBACK_STATUSES = {400, 403, 404, 405, 410, 501}


class LinkStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LinkCheck:
    status: LinkStatus
    reason: str


def valid_job_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        _ = parts.port
        host.encode("idna")
        return (
            parts.scheme.casefold() in {"http", "https"}
            and bool(host)
            and not any(character.isspace() or ord(character) < 32 for character in host)
        )
    except (UnicodeError, ValueError):
        return False


def _resolve_public_target(url: str, timeout_seconds: float) -> tuple[str, str]:
    parts = urlsplit(url)
    host = parts.hostname
    if not host:
        raise ValueError("missing host")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        results: queue.Queue[Sequence[tuple[Any, ...]] | OSError] = queue.Queue(maxsize=1)

        def resolve() -> None:
            try:
                results.put(socket.getaddrinfo(host, None, type=socket.SOCK_STREAM))
            except OSError as exc:
                results.put(exc)

        threading.Thread(target=resolve, daemon=True).start()
        try:
            resolved = results.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            raise TimeoutError("DNS resolution timed out") from exc
        if isinstance(resolved, OSError):
            raise resolved from None
        addresses = [ipaddress.ip_address(address[4][0]) for address in resolved]
    if not addresses or not all(address.is_global for address in addresses):
        raise ValueError("non-public target")

    address = str(addresses[0])
    netloc = f"[{address}]" if addresses[0].version == 6 else address
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, "")), host


def earliest_expiry(*values: object) -> object | None:
    parsed: list[tuple[datetime, object]] = []
    for value in values:
        if value in (None, ""):
            continue
        try:
            parsed.append((parse_datetime(value), value))
        except (TypeError, ValueError, OverflowError):
            continue
    return min(parsed, key=lambda item: item[0])[1] if parsed else None


def _expired(job: Job, now: datetime) -> str | None:
    for key in ("expiry_date", "close_at"):
        value = job.metadata.get(key)
        if value in (None, ""):
            continue
        try:
            expires_at = parse_datetime(value)
        except (TypeError, ValueError, OverflowError):
            LOGGER.debug("Ignoring invalid %s metadata for %s", key, job.source)
            continue
        if expires_at <= now:
            return key
    return None


def _request_status(
    http: HttpClient,
    method: str,
    url: str,
    deadline: float,
) -> int:
    for _ in range(6):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("link check timed out")
        request_url, host = _resolve_public_target(url, remaining)
        headers = {
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Host": host,
        }
        if method == "GET":
            headers["Range"] = "bytes=0-0"
        with http.client.stream(
            method,
            request_url,
            headers=headers,
            timeout=remaining,
            follow_redirects=False,
            extensions={"sni_hostname": host},
        ) as response:
            if response.is_redirect and (location := response.headers.get("Location")):
                url = urljoin(url, location)
                if not valid_job_url(url):
                    raise ValueError("invalid redirect")
                continue
            return response.status_code
    raise ValueError("too many redirects")


def check_job_link(
    job: Job,
    http: HttpClient,
    now: datetime,
    timeout_seconds: float,
    probe: bool = True,
) -> LinkCheck:
    if not valid_job_url(job.url):
        return LinkCheck(LinkStatus.UNAVAILABLE, "invalid URL")
    if expiry_field := _expired(job, now):
        return LinkCheck(LinkStatus.UNAVAILABLE, f"expired according to {expiry_field}")
    if not probe:
        return LinkCheck(LinkStatus.UNKNOWN, "network check disabled")

    deadline = time.monotonic() + timeout_seconds
    try:
        status = _request_status(http, "HEAD", job.url, deadline)
        if status in _GET_FALLBACK_STATUSES:
            status = _request_status(http, "GET", job.url, deadline)
    except (httpx.RequestError, httpx.InvalidURL, OSError, TimeoutError, ValueError) as exc:
        return LinkCheck(LinkStatus.UNKNOWN, type(exc).__name__)

    if status in _DEAD_STATUSES:
        return LinkCheck(LinkStatus.UNAVAILABLE, f"HTTP {status}")
    if 200 <= status < 400:
        return LinkCheck(LinkStatus.AVAILABLE, f"HTTP {status}")
    return LinkCheck(LinkStatus.UNKNOWN, f"HTTP {status}")
