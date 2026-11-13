from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from job_alert.http import HttpClient
from job_alert.models import Job
from job_alert.sources.common import html_to_text, parse_datetime, required

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
LEVER_URL = "https://api.lever.co/v0/postings/{slug}?mode=json"
ASHBY_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
SMARTRECRUITERS_URL = "https://api.smartrecruiters.com/v1/companies/{company}/postings"
SMARTRECRUITERS_DETAIL_URL = SMARTRECRUITERS_URL + "/{posting_id}"
RECRUITEE_URL = "https://{slug}.recruitee.com/api/offers/"


def parse_greenhouse(payload: dict[str, Any], slug: str, now: datetime | None = None) -> list[Job]:
    now = now or datetime.now(UTC)
    jobs: list[Job] = []
    for item in payload.get("jobs", []):
        location = item.get("location") or {}
        departments = item.get("departments") or []
        offices = item.get("offices") or []
        jobs.append(
            Job(
                source="greenhouse",
                source_id=str(required(item, "id")),
                url=str(required(item, "absolute_url")),
                title=str(required(item, "title")),
                company=slug,
                location=str(location.get("name", "")),
                description=html_to_text(item.get("content")),
                posted_at=parse_datetime(required(item, "first_published")),
                observed_at=now,
                metadata={
                    "departments": [d.get("name", "") for d in departments],
                    "offices": [o.get("name", "") for o in offices],
                },
            )
        )
    return jobs


def fetch_greenhouse(http: HttpClient, slug: str, now: datetime | None = None) -> list[Job]:
    payload = http.get_json(GREENHOUSE_URL.format(slug=slug))
    if not isinstance(payload, dict):
        raise ValueError("invalid Greenhouse response")
    return parse_greenhouse(payload, slug, now)


def parse_lever(payload: list[dict[str, Any]], slug: str, now: datetime | None = None) -> list[Job]:
    now = now or datetime.now(UTC)
    jobs: list[Job] = []
    for item in payload:
        categories = item.get("categories") or {}
        lists = item.get("lists") or []
        body = " ".join(
            (
                html_to_text(item.get("descriptionPlain") or item.get("description")),
                *(html_to_text(entry.get("content")) for entry in lists),
                html_to_text(item.get("additionalPlain") or item.get("additional")),
            )
        )
        jobs.append(
            Job(
                source="lever",
                source_id=str(required(item, "id")),
                url=str(required(item, "hostedUrl")),
                title=str(required(item, "text")),
                company=slug,
                location=str(categories.get("location", "")),
                description=body,
                posted_at=parse_datetime(item.get("createdAt"), now),
                observed_at=now,
                work_mode=str(item.get("workplaceType", "")),
                metadata={"team": categories.get("team", "")},
            )
        )
    return jobs


def fetch_lever(http: HttpClient, slug: str, now: datetime | None = None) -> list[Job]:
    payload = http.get_json(LEVER_URL.format(slug=slug))
    if not isinstance(payload, list):
        raise ValueError("invalid Lever response")
    return parse_lever(payload, slug, now)


def parse_ashby(payload: dict[str, Any], slug: str, now: datetime | None = None) -> list[Job]:
    now = now or datetime.now(UTC)
    jobs: list[Job] = []
    for item in payload.get("jobs", []):
        location = str(item.get("location", ""))
        jobs.append(
            Job(
                source="ashby",
                source_id=str(item.get("id") or item.get("jobUrl") or item.get("title")),
                url=str(required(item, "jobUrl")),
                title=str(required(item, "title")),
                company=slug,
                location=location,
                description=html_to_text(
                    item.get("descriptionHtml") or item.get("descriptionPlain") or item.get("description")
                ),
                posted_at=parse_datetime(required(item, "publishedAt")),
                observed_at=now,
                work_mode="remote" if item.get("isRemote") else "",
                metadata={"department": item.get("department", "")},
            )
        )
    return jobs


def fetch_ashby(http: HttpClient, slug: str, now: datetime | None = None) -> list[Job]:
    payload = http.get_json(ASHBY_URL.format(slug=slug))
    if not isinstance(payload, dict):
        raise ValueError("invalid Ashby response")
    return parse_ashby(payload, slug, now)


def _smartrecruiters_location(item: dict[str, Any]) -> str:
    location = item.get("location") or {}
    if not isinstance(location, dict):
        return str(location)
    return ", ".join(
        str(location[key])
        for key in ("city", "region", "country")
        if location.get(key)
    )


def _smartrecruiters_description(item: dict[str, Any]) -> str:
    job_ad = item.get("jobAd") or {}
    sections = job_ad.get("sections", {}) if isinstance(job_ad, dict) else {}
    if not isinstance(sections, dict):
        return ""
    values: list[str] = []
    for key in (
        "companyDescription",
        "jobDescription",
        "qualifications",
        "additionalInformation",
    ):
        section = sections.get(key)
        if isinstance(section, dict):
            values.append(html_to_text(section.get("text") or section.get("content")))
        elif isinstance(section, str):
            values.append(html_to_text(section))
    return " ".join(value for value in values if value)


def parse_smartrecruiters(
    payload: dict[str, Any],
    company: str,
    now: datetime | None = None,
) -> list[Job]:
    now = now or datetime.now(UTC)
    items = payload.get("content", [])
    if not isinstance(items, list):
        raise ValueError("invalid SmartRecruiters postings")
    jobs: list[Job] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("invalid SmartRecruiters posting")
        company_data = item.get("company") or {}
        location = item.get("location") or {}
        jobs.append(
            Job(
                source="smartrecruiters",
                source_id=str(required(item, "id")),
                url=str(item.get("postingUrl") or item.get("applyUrl") or required(item, "id")),
                title=str(required(item, "name")),
                company=str(company_data.get("name", company))
                if isinstance(company_data, dict)
                else company,
                location=_smartrecruiters_location(item),
                description=_smartrecruiters_description(item),
                posted_at=parse_datetime(required(item, "releasedDate")),
                observed_at=now,
                work_mode=(
                    "remote"
                    if isinstance(location, dict) and location.get("remote")
                    else "hybrid"
                    if isinstance(location, dict) and location.get("hybrid")
                    else ""
                ),
                metadata={"company_identifier": company},
            )
        )
    return jobs


def fetch_smartrecruiters(
    http: HttpClient,
    company: str,
    now: datetime | None = None,
) -> list[Job]:
    content: list[dict[str, Any]] = []
    offset = 0
    for _ in range(100):
        payload = http.get_json(
            SMARTRECRUITERS_URL.format(company=company),
            params={"destination": "PUBLIC", "limit": 100, "offset": offset},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("content", []), list):
            raise ValueError("invalid SmartRecruiters response")
        page = payload.get("content", [])
        for summary in page:
            if not isinstance(summary, dict):
                raise ValueError("invalid SmartRecruiters posting")
            posting = summary
            if not _smartrecruiters_description(summary):
                posting_id = str(required(summary, "id"))
                try:
                    detail = http.get_json(
                        SMARTRECRUITERS_DETAIL_URL.format(company=company, posting_id=posting_id)
                    )
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in {404, 410}:
                        continue
                    raise
                if not isinstance(detail, dict):
                    raise ValueError("invalid SmartRecruiters detail")
                posting = {**summary, **detail}
            content.append(posting)
        offset += len(page)
        if not page or offset >= int(payload.get("totalFound", offset)):
            return parse_smartrecruiters({"content": content}, company, now)
    raise ValueError("SmartRecruiters pagination exceeded 100 pages")


def _recruitee_locations(item: dict[str, Any]) -> str:
    raw = item.get("locations") or item.get("location") or []
    locations = raw if isinstance(raw, list) else [raw]
    values: list[str] = []
    for location in locations:
        if isinstance(location, dict):
            text = ", ".join(
                str(location[key])
                for key in ("name", "city", "state", "country")
                if location.get(key)
            )
            if note := location.get("note"):
                text = " ".join((text, str(note)))
        else:
            text = str(location) if location else ""
        if text:
            values.append(text)
    return "; ".join(dict.fromkeys(values))


def parse_recruitee(
    payload: dict[str, Any],
    slug: str,
    now: datetime | None = None,
) -> list[Job]:
    now = now or datetime.now(UTC)
    items = payload.get("offers", [])
    if not isinstance(items, list):
        raise ValueError("invalid Recruitee offers")
    jobs: list[Job] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("invalid Recruitee offer")
        if item.get("status") not in (None, "published"):
            continue
        description = " ".join(
            value
            for value in (
                html_to_text(item.get("description")),
                html_to_text(item.get("requirements")),
                html_to_text(item.get("highlight")),
            )
            if value
        )
        jobs.append(
            Job(
                source="recruitee",
                source_id=str(item.get("id") or required(item, "guid")),
                url=str(item.get("careers_url") or item.get("careers_apply_url") or required(item, "guid")),
                title=str(required(item, "title")),
                company=str(item.get("company_name", slug)),
                location=_recruitee_locations(item),
                description=description,
                posted_at=parse_datetime(item.get("published_at") or item.get("created_at"), now),
                observed_at=now,
                work_mode=(
                    "remote" if item.get("remote") else "hybrid" if item.get("hybrid") else ""
                ),
                metadata={
                    "tenant": slug,
                    "close_at": item.get("close_at"),
                    "tags": item.get("tags", []),
                },
            )
        )
    return jobs


def fetch_recruitee(
    http: HttpClient,
    slug: str,
    now: datetime | None = None,
    token: str | None = None,
) -> list[Job]:
    headers = {"X-Careers-Sites-Token": token} if token else None
    payload = http.get_json(RECRUITEE_URL.format(slug=slug), headers=headers)
    if not isinstance(payload, dict):
        raise ValueError("invalid Recruitee response")
    return parse_recruitee(payload, slug, now)
