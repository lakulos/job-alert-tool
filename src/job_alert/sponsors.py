from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from job_alert.http import HttpClient
from job_alert.models import Evidence, Job, Sponsorship

PUBLICATION_URL = (
    "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
)
_LEGAL_SUFFIXES = re.compile(
    r"\b(?:limited|ltd|plc|llp|incorporated|inc|corporation|corp|company|co)\b", re.I
)


def normalize_company_name(name: str) -> str:
    value = _LEGAL_SUFFIXES.sub(" ", name)
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def parse_sponsor_names(csv_text: str) -> set[str]:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("﻿")))
    if "Organisation Name" not in (reader.fieldnames or []):
        raise ValueError("sponsor CSV is missing Organisation Name")
    return {
        normalized
        for row in reader
        if (normalized := normalize_company_name(row.get("Organisation Name", "")))
    }


def find_csv_url(publication_html: str) -> str:
    soup = BeautifulSoup(publication_html, "html.parser")
    for anchor in soup.select('a[href*="assets.publishing.service.gov.uk"][href$=".csv"]'):
        href = anchor.get("href")
        if isinstance(href, str):
            return urljoin(PUBLICATION_URL, href)
    raise ValueError("could not find sponsor CSV on GOV.UK publication page")


class SponsorRegister:
    def __init__(self, cache_dir: Path, http: HttpClient) -> None:
        self.cache_file = cache_dir / "uk-sponsors.csv"
        self.meta_file = cache_dir / "uk-sponsors.json"
        self.http = http

    def load(self, now: datetime | None = None) -> set[str]:
        now = now or datetime.now(UTC)
        if self._is_fresh(now):
            return parse_sponsor_names(self.cache_file.read_text(encoding="utf-8-sig"))
        try:
            publication = self.http.get_text(PUBLICATION_URL)
            csv_url = find_csv_url(publication)
            csv_text = self.http.get_text(csv_url)
            names = parse_sponsor_names(csv_text)
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(csv_text, encoding="utf-8")
            self.meta_file.write_text(
                json.dumps({"refreshed_at": now.isoformat(), "url": csv_url}),
                encoding="utf-8",
            )
            return names
        except Exception:
            if self.cache_file.exists():
                return parse_sponsor_names(self.cache_file.read_text(encoding="utf-8-sig"))
            raise

    def _is_fresh(self, now: datetime) -> bool:
        if not self.cache_file.exists() or not self.meta_file.exists():
            return False
        try:
            refreshed = datetime.fromisoformat(
                json.loads(self.meta_file.read_text(encoding="utf-8"))["refreshed_at"]
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return False
        return now - refreshed.astimezone(UTC) < timedelta(days=7)


def apply_sponsor_match(job: Job, sponsors: set[str]) -> Job:
    if job.sponsorship.value != Sponsorship.UNCLEAR:
        return job
    normalized = normalize_company_name(job.company)
    if normalized and normalized in sponsors:
        job.sponsorship = Evidence(Sponsorship.LIKELY, f'UK sponsor register: "{job.company}"')
    return job
