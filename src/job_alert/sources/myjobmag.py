from __future__ import annotations

from datetime import UTC, datetime

import feedparser

from job_alert.http import HttpClient
from job_alert.models import Job
from job_alert.sources.common import html_to_text, parse_datetime, required


def parse_myjobmag(xml_text: str, now: datetime | None = None) -> list[Job]:
    now = now or datetime.now(UTC)
    feed = feedparser.parse(xml_text)
    if feed.bozo and not feed.entries:
        raise ValueError(f"invalid MyJobMag RSS: {feed.bozo_exception}")
    jobs: list[Job] = []
    for item in feed.entries:
        title = str(item.get("position") or item.get("title") or "")
        company = str(item.get("company") or "")
        if not item.get("position") and " at " in title:
            title, _, company = title.rpartition(" at ")
        jobs.append(
            Job(
                source="myjobmag_rss",
                source_id=str(item.get("id") or item.get("guid") or required(item, "link")),
                url=str(required(item, "link")),
                title=title.strip(),
                company=company.strip(),
                location=str(item.get("location", "Nigeria")),
                description=html_to_text(item.get("description")),
                posted_at=parse_datetime(required(item, "published")),
                observed_at=now,
                metadata={"nigeria_query": True, "attribution": "MyJobMag"},
            )
        )
    return jobs


def fetch_myjobmag(http: HttpClient, url: str, now: datetime | None = None) -> list[Job]:
    return parse_myjobmag(http.get_text(url), now)
