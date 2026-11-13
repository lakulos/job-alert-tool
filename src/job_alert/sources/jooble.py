from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from job_alert.http import HttpClient
from job_alert.models import Job
from job_alert.sources.common import html_to_text, parse_datetime, required

ROLE_QUERIES = ("Cloud Engineer", "Cloud Architect", "DevOps Engineer", "Site Reliability Engineer")
TRACK_QUERIES = {
    "remote_worldwide": ("remote worldwide", ""),
    "visa_or_relocation": ("visa sponsorship relocation", ""),
}


def parse_jooble(
    payload: dict[str, Any],
    now: datetime | None = None,
    track: str = "",
) -> list[Job]:
    now = now or datetime.now(UTC)
    jobs: list[Job] = []
    for item in payload.get("jobs", []):
        jobs.append(
            Job(
                source="jooble",
                source_id=str(item.get("id") or required(item, "link")),
                url=str(required(item, "link")),
                title=str(required(item, "title")),
                company=str(item.get("company", "")),
                location=str(item.get("location", "")),
                description=html_to_text(item.get("snippet")),
                posted_at=parse_datetime(required(item, "updated")),
                observed_at=now,
                work_mode="remote" if "remote" in str(item.get("type", "")).casefold() else "",
                metadata={"jooble_track": track},
            )
        )
    return jobs


def fetch_jooble(
    http: HttpClient,
    api_base: str,
    api_key: str,
    now: datetime | None = None,
) -> list[Job]:
    all_jobs: list[Job] = []
    endpoint = f"{api_base.rstrip('/')}/{api_key}"
    for role in ROLE_QUERIES:
        for track, (suffix, location) in TRACK_QUERIES.items():
            payload = http.post_json(
                endpoint,
                json={"keywords": " ".join(part for part in (role, suffix) if part), "location": location},
            )
            if not isinstance(payload, dict):
                raise ValueError("invalid Jooble response")
            all_jobs.extend(parse_jooble(payload, now, track))
    return all_jobs
