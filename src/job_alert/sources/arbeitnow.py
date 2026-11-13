from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from job_alert.http import HttpClient
from job_alert.models import Job
from job_alert.sources.common import html_to_text, parse_datetime, required

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"


def parse_arbeitnow(
    payload: dict[str, Any],
    now: datetime | None = None,
    sponsorship_filtered: bool = True,
) -> list[Job]:
    now = now or datetime.now(UTC)
    jobs: list[Job] = []
    for item in payload.get("data", []):
        slug = str(required(item, "slug"))
        jobs.append(
            Job(
                source="arbeitnow",
                source_id=slug,
                url=str(item.get("url") or f"https://www.arbeitnow.com/jobs/{slug}"),
                title=str(required(item, "title")),
                company=str(required(item, "company_name")),
                location=str(item.get("location", "")),
                description=html_to_text(item.get("description")),
                posted_at=parse_datetime(required(item, "created_at")),
                observed_at=now,
                work_mode="remote" if item.get("remote") else "",
                metadata={
                    "tags": item.get("tags", []),
                    "sponsorship_filtered": sponsorship_filtered,
                },
            )
        )
    return jobs


def fetch_arbeitnow(http: HttpClient, now: datetime | None = None) -> list[Job]:
    payload = http.get_json(ARBEITNOW_URL, params={"visa_sponsorship": "true"})
    if not isinstance(payload, dict):
        raise ValueError("invalid Arbeitnow response")
    return parse_arbeitnow(payload, now, sponsorship_filtered=True)
