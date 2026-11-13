from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from job_alert.http import HttpClient
from job_alert.models import Job
from job_alert.sources.common import html_to_text, parse_datetime, required

APIFY_RUN_URL = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"


def parse_apify(
    payload: list[dict[str, Any]],
    board: str,
    now: datetime | None = None,
) -> list[Job]:
    now = now or datetime.now(UTC)
    jobs: list[Job] = []
    for item in payload:
        url = item.get("url") or item.get("jobUrl") or item.get("applyUrl")
        posted_at = item.get("postedAt") or item.get("date")
        jobs.append(
            Job(
                source=f"apify:{board}",
                source_id=str(item.get("id") or url),
                url=str(required({"url": url}, "url")),
                title=str(required(item, "title")),
                company=str(item.get("company") or item.get("companyName") or ""),
                location=str(item.get("location", "")),
                description=html_to_text(item.get("description")),
                posted_at=parse_datetime(required({"posted_at": posted_at}, "posted_at")),
                observed_at=now,
                work_mode=str(item.get("workMode", "")),
                metadata={"apify_actor_board": board},
            )
        )
    return jobs


def fetch_apify(
    http: HttpClient,
    board: str,
    actor: str,
    token: str,
    actor_input: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> list[Job]:
    payload = http.request(
        "POST",
        APIFY_RUN_URL.format(actor=actor),
        params={"token": token},
        json=actor_input or {},
    ).json()
    if not isinstance(payload, list):
        raise ValueError("invalid Apify dataset response")
    return parse_apify(payload, board, now)
