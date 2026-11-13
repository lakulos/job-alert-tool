from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from job_alert.config import AppConfig
from job_alert.dedupe import merge_jobs
from job_alert.email_alerts.imap import fetch_gmail_alerts
from job_alert.email_alerts.parser import sender_rules
from job_alert.filters import assign_tracks, classify_job, is_fresh, title_is_allowed
from job_alert.http import HttpClient
from job_alert.models import Job, SourceResult
from job_alert.sources.apify import fetch_apify
from job_alert.sources.arbeitnow import fetch_arbeitnow, parse_arbeitnow
from job_alert.sources.ats import (
    fetch_ashby,
    fetch_greenhouse,
    fetch_lever,
    fetch_recruitee,
    fetch_smartrecruiters,
    parse_ashby,
    parse_greenhouse,
    parse_lever,
    parse_recruitee,
    parse_smartrecruiters,
)
from job_alert.sources.jooble import fetch_jooble, parse_jooble
from job_alert.sources.myjobmag import fetch_myjobmag, parse_myjobmag
from job_alert.sources.remote import (
    fetch_himalayas,
    fetch_jobicy,
    fetch_remote_ok,
    fetch_remotive,
    fetch_wwr,
    parse_himalayas,
    parse_jobicy,
    parse_remote_ok,
    parse_remotive,
    parse_wwr,
)
from job_alert.sponsors import SponsorRegister, apply_sponsor_match

LOGGER = logging.getLogger(__name__)


class AllSourcesFailed(RuntimeError):
    pass


class Collector:
    def __init__(
        self,
        config: AppConfig,
        http: HttpClient,
        processed_message_ids: set[str],
        fixtures: Path | None = None,
        now: datetime | None = None,
    ) -> None:
        self.config = config
        self.http = http
        self.processed_message_ids = processed_message_ids
        self.fixtures = fixtures
        self.now = now or datetime.now(UTC)
        self.results: list[SourceResult] = []
        self.attempted = 0
        self.succeeded = 0

    def _run(self, source: str, callback: Callable[[], list[Job]]) -> None:
        self.attempted += 1
        try:
            self.results.append(SourceResult(source=source, jobs=callback()))
            self.succeeded += 1
        except Exception as exc:
            LOGGER.exception("Source %s failed: %s", source, exc)
            self.results.append(SourceResult(source=source, error=str(exc)))

    def collect(self) -> list[SourceResult]:
        if self.fixtures:
            self._collect_fixtures()
        else:
            self._collect_live()
        if self.attempted and not self.succeeded:
            raise AllSourcesFailed("all enabled sources failed")
        return self.results

    def _enabled(self, name: str) -> dict[str, Any] | None:
        value = self.config.sources.get(name, {})
        return value if value.get("enabled", False) else None

    def _collect_live(self) -> None:
        if (source := self._enabled("greenhouse")) is not None:
            for slug in source.get("slugs", []):
                self._run(
                    f"greenhouse:{slug}",
                    lambda slug=slug: fetch_greenhouse(self.http, slug, self.now),  # type: ignore[misc]
                )
        if (source := self._enabled("lever")) is not None:
            for slug in source.get("slugs", []):
                self._run(
                    f"lever:{slug}",
                    lambda slug=slug: fetch_lever(self.http, slug, self.now),  # type: ignore[misc]
                )
        if (source := self._enabled("ashby")) is not None:
            for slug in source.get("slugs", []):
                self._run(
                    f"ashby:{slug}",
                    lambda slug=slug: fetch_ashby(self.http, slug, self.now),  # type: ignore[misc]
                )
        if (source := self._enabled("smartrecruiters")) is not None:
            for company in source.get("companies", []):
                self._run(
                    f"smartrecruiters:{company}",
                    lambda company=company: fetch_smartrecruiters(  # type: ignore[misc]
                        self.http, company, self.now
                    ),
                )
        if (source := self._enabled("recruitee")) is not None:
            for tenant in source.get("tenants", []):
                if isinstance(tenant, str):
                    slug, token_env = tenant, ""
                else:
                    slug = str(tenant["slug"])
                    token_env = str(tenant.get("token_env", ""))
                token = os.getenv(token_env) if token_env else None
                self._run(
                    f"recruitee:{slug}",
                    lambda slug=slug, token=token: fetch_recruitee(  # type: ignore[misc]
                        self.http, slug, self.now, token
                    ),
                )
        if self._enabled("remote_ok") is not None:
            self._run("remote_ok", lambda: fetch_remote_ok(self.http, self.now))
        if self._enabled("jobicy") is not None:
            self._run("jobicy", lambda: fetch_jobicy(self.http, self.now))
        if self._enabled("himalayas") is not None:
            self._run(
                "himalayas",
                lambda: fetch_himalayas(
                    self.http, self.now, self.config.freshness_hours
                ),
            )
        if self._enabled("remotive") is not None:
            self._run("remotive", lambda: fetch_remotive(self.http, self.now))
        if (source := self._enabled("we_work_remotely")) is not None:
            for feed in source.get("feeds", []):
                self._run(
                    "we_work_remotely",
                    lambda feed=feed: fetch_wwr(self.http, feed, self.now),  # type: ignore[misc]
                )
        if self._enabled("arbeitnow") is not None:
            self._run("arbeitnow", lambda: fetch_arbeitnow(self.http, self.now))
        if (source := self._enabled("myjobmag_rss")) is not None:
            myjobmag_url = str(source["url"])
            self._run("myjobmag_rss", lambda: fetch_myjobmag(self.http, myjobmag_url, self.now))
        if (source := self._enabled("jooble")) is not None:
            if api_key := os.getenv("JOOBLE_API_KEY"):
                jooble_base = str(source["api_base"])
                self._run(
                    "jooble",
                    lambda: fetch_jooble(self.http, jooble_base, api_key, self.now),
                )
            else:
                LOGGER.info("Skipping Jooble: JOOBLE_API_KEY is not set")
        if (source := self._enabled("apify")) is not None:
            if token := os.getenv("APIFY_TOKEN"):
                for board, actor_config in source.get("actors", {}).items():
                    if isinstance(actor_config, str):
                        actor, actor_input = actor_config, {}
                    else:
                        actor = actor_config["actor"]
                        actor_input = actor_config.get("input", {})
                    self._run(
                        f"apify:{board}",
                        lambda board=board, actor=actor, actor_input=actor_input: fetch_apify(  # type: ignore[misc]
                            self.http, board, actor, token, actor_input, self.now
                        ),
                    )
            else:
                LOGGER.info("Skipping Apify: APIFY_TOKEN is not set")
        if self._enabled("gmail_alerts") is not None:
            address, password = os.getenv("GMAIL_ADDRESS"), os.getenv("GMAIL_APP_PASSWORD")
            if address and password:
                self.attempted += 1
                try:
                    result = fetch_gmail_alerts(
                        address,
                        password,
                        sender_rules(self.config.alert_senders, self.config.email_rules),
                        self.processed_message_ids,
                        self.now,
                    )
                    self.results.append(result)
                    self.succeeded += 1
                except Exception as exc:
                    LOGGER.exception("Source gmail_alerts failed: %s", exc)
                    self.results.append(SourceResult(source="gmail_alerts", error=str(exc)))
            else:
                LOGGER.info("Skipping Gmail alerts: Gmail credentials are not set")

    def _collect_fixtures(self) -> None:
        assert self.fixtures is not None
        parsers: dict[str, Callable[[Any], list[Job]]] = {
            "greenhouse.json": lambda data: parse_greenhouse(data, "fixture-company", self.now),
            "lever.json": lambda data: parse_lever(data, "fixture-company", self.now),
            "ashby.json": lambda data: parse_ashby(data, "fixture-company", self.now),
            "smartrecruiters.json": lambda data: parse_smartrecruiters(
                data, "fixture-company", self.now
            ),
            "recruitee.json": lambda data: parse_recruitee(data, "fixture-company", self.now),
            "remote_ok.json": lambda data: parse_remote_ok(data, self.now),
            "jobicy.json": lambda data: parse_jobicy(data, self.now),
            "himalayas.json": lambda data: parse_himalayas(data, self.now),
            "remotive.json": lambda data: parse_remotive(data, self.now),
            "arbeitnow.json": lambda data: parse_arbeitnow(data, self.now),
            "jooble.json": lambda data: parse_jooble(data, self.now, "nigeria"),
        }
        for filename, parser in parsers.items():
            path = self.fixtures / filename
            if path.exists():
                self._run(
                    filename,
                    lambda path=path, parser=parser: parser(  # type: ignore[misc]
                        json.loads(path.read_text())
                    ),
                )
        for filename, parser in (
            ("wwr.xml", parse_wwr),
            ("myjobmag.xml", parse_myjobmag),
        ):
            path = self.fixtures / filename
            if path.exists():
                self._run(
                    filename,
                    lambda path=path, parser=parser: parser(  # type: ignore[misc]
                        path.read_text(), self.now
                    ),
                )


def filter_and_classify(
    results: list[SourceResult],
    config: AppConfig,
    sent_urls: set[str],
    http: HttpClient,
    now: datetime | None = None,
    use_sponsor_register: bool = True,
) -> list[Job]:
    now = now or datetime.now(UTC)
    candidates = [job for result in results for job in result.jobs]
    selected: list[Job] = []
    for job in candidates:
        if not title_is_allowed(job.title, config):
            continue
        if not is_fresh(job, now, config.freshness_hours):
            continue
        selected.append(classify_job(job, config))
    merged = [job for job in merge_jobs(selected) if job.url not in sent_urls]
    sponsors: set[str] = set()
    if use_sponsor_register:
        try:
            sponsors = SponsorRegister(config.cache_dir, http).load(now)
        except Exception as exc:
            LOGGER.warning("UK sponsor register unavailable: %s", exc)
    for job in merged:
        apply_sponsor_match(job, sponsors)
        assign_tracks(job)
    return [job for job in merged if job.tracks]
