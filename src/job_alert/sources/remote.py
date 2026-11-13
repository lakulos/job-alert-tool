from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import feedparser

from job_alert.http import HttpClient
from job_alert.models import Job
from job_alert.sources.common import html_to_text, parse_datetime, required

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
REMOTE_OK_URL = "https://remoteok.com/api"
JOBICY_URL = "https://jobicy.com/api/jobs"
HIMALAYAS_URL = "https://himalayas.app/jobs/api"


def parse_remotive(payload: dict[str, Any], now: datetime | None = None) -> list[Job]:
    now = now or datetime.now(UTC)
    jobs: list[Job] = []
    for item in payload.get("jobs", []):
        jobs.append(
            Job(
                source="remotive",
                source_id=str(required(item, "id")),
                url=str(required(item, "url")),
                title=str(required(item, "title")),
                company=str(required(item, "company_name")),
                location=str(item.get("candidate_required_location", "")),
                description=html_to_text(item.get("description")),
                posted_at=parse_datetime(required(item, "publication_date")),
                observed_at=now,
                work_mode="remote",
                metadata={"attribution": "Remotive", "tags": item.get("tags", [])},
            )
        )
    return jobs


def fetch_remotive(http: HttpClient, now: datetime | None = None) -> list[Job]:
    payload = http.get_json(REMOTIVE_URL)
    if not isinstance(payload, dict):
        raise ValueError("invalid Remotive response")
    return parse_remotive(payload, now)


def parse_remote_ok(payload: list[dict[str, Any]], now: datetime | None = None) -> list[Job]:
    now = now or datetime.now(UTC)
    jobs: list[Job] = []
    for item in payload:
        if "legal" in item and "id" not in item:
            continue
        jobs.append(
            Job(
                source="remote_ok",
                source_id=str(required(item, "id")),
                url=str(required(item, "url")),
                title=str(required(item, "position")),
                company=str(item.get("company", "")),
                location=str(item.get("location", "")),
                description=html_to_text(item.get("description")),
                posted_at=parse_datetime(item.get("epoch") or required(item, "date")),
                observed_at=now,
                work_mode="remote",
                metadata={"attribution": "Remote OK", "tags": item.get("tags", [])},
            )
        )
    return jobs


def fetch_remote_ok(http: HttpClient, now: datetime | None = None) -> list[Job]:
    payload = http.get_json(REMOTE_OK_URL)
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError("invalid Remote OK response")
    return parse_remote_ok(payload, now)


def parse_jobicy(payload: dict[str, Any], now: datetime | None = None) -> list[Job]:
    now = now or datetime.now(UTC)
    items = payload.get("jobs", [])
    if not isinstance(items, list):
        raise ValueError("invalid Jobicy jobs")
    jobs: list[Job] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("invalid Jobicy job")
        jobs.append(
            Job(
                source="jobicy",
                source_id=str(required(item, "id")),
                url=str(required(item, "url")),
                title=str(required(item, "jobTitle")),
                company=str(item.get("companyName", "")),
                location=str(item.get("jobGeo", "")),
                description=html_to_text(item.get("jobDescription") or item.get("jobExcerpt")),
                posted_at=parse_datetime(required(item, "pubDate")),
                observed_at=now,
                work_mode="remote",
                metadata={
                    "attribution": "Jobicy",
                    "industries": item.get("jobIndustry", []),
                    "job_types": item.get("jobType", []),
                },
            )
        )
    return jobs


def fetch_jobicy(http: HttpClient, now: datetime | None = None) -> list[Job]:
    jobs: list[Job] = []
    cursor: str | None = None
    for _ in range(20):
        params: dict[str, int | str] = {"count": 100}
        if cursor:
            params["cursor"] = cursor
        payload = http.get_json(JOBICY_URL, params=params)
        if not isinstance(payload, dict):
            raise ValueError("invalid Jobicy response")
        jobs.extend(parse_jobicy(payload, now))
        next_cursor = payload.get("nextCursor")
        if not payload.get("hasMore") or not next_cursor:
            return jobs
        cursor = str(next_cursor)
    raise ValueError("Jobicy pagination exceeded 20 pages")


def _restrictions(item: dict[str, Any]) -> str:
    values: list[str] = []
    for field in ("locationRestrictions", "timezoneRestrictions"):
        raw = item.get(field) or []
        if isinstance(raw, list):
            values.extend(str(value) for value in raw if value)
        elif raw:
            values.append(str(raw))
    return ", ".join(dict.fromkeys(values))


def parse_himalayas(payload: dict[str, Any], now: datetime | None = None) -> list[Job]:
    now = now or datetime.now(UTC)
    items = payload.get("jobs", [])
    if not isinstance(items, list):
        raise ValueError("invalid Himalayas jobs")
    jobs: list[Job] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("invalid Himalayas job")
        restrictions = _restrictions(item)
        description = " ".join(
            value
            for value in (
                html_to_text(item.get("description") or item.get("excerpt")),
                f"Remote within {restrictions}" if restrictions else "",
            )
            if value
        )
        jobs.append(
            Job(
                source="himalayas",
                source_id=str(required(item, "guid")),
                url=str(required(item, "applicationLink")),
                title=str(required(item, "title")),
                company=str(item.get("companyName", "")),
                location=restrictions,
                description=description,
                posted_at=parse_datetime(required(item, "pubDate")),
                observed_at=now,
                work_mode="remote",
                metadata={
                    "attribution": "Himalayas",
                    "categories": item.get("categories", []),
                    "expiry_date": item.get("expiryDate"),
                },
            )
        )
    return jobs


def fetch_himalayas(
    http: HttpClient,
    now: datetime | None = None,
    freshness_hours: int = 48,
) -> list[Job]:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=freshness_hours)
    jobs: list[Job] = []
    cursor: str | None = None
    for _ in range(20):
        params = {"cursor": cursor} if cursor else None
        payload = http.get_json(HIMALAYAS_URL, params=params)
        if not isinstance(payload, dict):
            raise ValueError("invalid Himalayas response")
        page = parse_himalayas(payload, now)
        jobs.extend(page)
        if page and min(job.posted_at for job in page) < cutoff:
            return jobs
        next_cursor = payload.get("nextCursor")
        if not next_cursor:
            return jobs
        cursor = str(next_cursor)
    raise ValueError("Himalayas pagination exceeded 20 pages")


def parse_wwr(xml_text: str, now: datetime | None = None) -> list[Job]:
    now = now or datetime.now(UTC)
    feed = feedparser.parse(xml_text)
    if feed.bozo and not feed.entries:
        raise ValueError(f"invalid WWR RSS: {feed.bozo_exception}")
    jobs: list[Job] = []
    for item in feed.entries:
        title = str(item.get("title", ""))
        company, separator, role = title.partition(":")
        jobs.append(
            Job(
                source="we_work_remotely",
                source_id=str(item.get("id") or item.get("guid") or required(item, "link")),
                url=str(required(item, "link")),
                title=role.strip() if separator else title.strip(),
                company=company.strip() if separator else "",
                location=str(item.get("region") or item.get("country") or ""),
                description=html_to_text(item.get("description")),
                posted_at=parse_datetime(required(item, "published")),
                observed_at=now,
                work_mode="remote",
                metadata={"attribution": "We Work Remotely"},
            )
        )
    return jobs


def fetch_wwr(http: HttpClient, feed_url: str, now: datetime | None = None) -> list[Job]:
    return parse_wwr(http.get_text(feed_url), now)
