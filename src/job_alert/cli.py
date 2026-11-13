from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from job_alert.config import ConfigError, load_config
from job_alert.digest import build_digest, create_message, render_digest
from job_alert.http import HttpClient
from job_alert.logging import configure_logging
from job_alert.mailer import send_gmail
from job_alert.models import Job
from job_alert.pipeline import AllSourcesFailed, Collector, filter_and_classify
from job_alert.state import StateStore

LOGGER = logging.getLogger(__name__)


def message_ids_safe_to_mark(
    jobs: list[Job], included_urls: set[str], all_message_ids: set[str]
) -> set[str]:
    omitted_message_ids: set[str] = set()
    for job in jobs:
        if job.url in included_urls:
            continue
        if message_id := job.metadata.get("message_id"):
            omitted_message_ids.add(str(message_id))
        omitted_message_ids.update(str(value) for value in job.metadata.get("message_ids", []))
    return all_message_ids - omitted_message_ids


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Email Cloud, DevOps, and SRE job alerts")
    result.add_argument("--config", default="config.yaml", help="path to config.yaml")
    result.add_argument("--dry-run", action="store_true", help="write digest.html and send nothing")
    result.add_argument("--fixtures", type=Path, help="offline fixture directory (implies no network)")
    result.add_argument("--output", type=Path, help="dry-run HTML output path")
    result.add_argument("--verbose", action="store_true")
    return result


def run(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    # Dry runs remain credential-free and do not need .env. Live mode loads it quietly.
    if not args.dry_run:
        load_dotenv(config.path.parent / ".env")
    configured_secrets = [
        os.getenv("GMAIL_APP_PASSWORD", ""),
        os.getenv("APIFY_TOKEN", ""),
        os.getenv("JOOBLE_API_KEY", ""),
    ]
    for tenant in config.sources.get("recruitee", {}).get("tenants", []):
        if isinstance(tenant, dict) and (token_env := tenant.get("token_env")):
            configured_secrets.append(os.getenv(str(token_env), ""))
    configure_logging(args.verbose, tuple(configured_secrets))

    with StateStore(config.state_path) as state, HttpClient(
        config.http.timeout_seconds,
        config.http.retries,
        config.http.user_agent,
    ) as http:
        try:
            results = Collector(
                config,
                http,
                state.processed_message_ids(),
                fixtures=args.fixtures,
            ).collect()
        except AllSourcesFailed as exc:
            LOGGER.error("%s", exc)
            return 3

        fixture_jobs = [job for result in results for job in result.jobs]
        evaluation_now = max((job.posted_at for job in fixture_jobs), default=None) if args.fixtures else None
        jobs = filter_and_classify(
            results,
            config,
            state.sent_urls(),
            http,
            now=evaluation_now,
            use_sponsor_register=not bool(args.fixtures),
        )
        unparsed = [alert for result in results for alert in result.unparsed_alerts]
        all_message_ids = {message_id for result in results for message_id in result.message_ids}
        digest = build_digest(jobs, unparsed, config.max_jobs_per_email)
        if not digest.has_content:
            LOGGER.info("No new matching jobs or unparsed alerts; no email sent")
            return 0

        html, text = render_digest(digest)
        if args.dry_run:
            output = (args.output or (config.path.parent / "digest.html")).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(html, encoding="utf-8")
            LOGGER.info("Dry-run digest written to %s", output)
            return 0

        address = os.getenv("GMAIL_ADDRESS", "")
        password = os.getenv("GMAIL_APP_PASSWORD", "")
        recipient = os.getenv("DIGEST_TO") or address
        if not address or not password or not recipient:
            LOGGER.error("GMAIL_ADDRESS and GMAIL_APP_PASSWORD are required to send")
            return 2
        message = create_message(digest, address, recipient, html, text)
        try:
            send_gmail(address, password, message)
        except Exception as exc:
            LOGGER.error("Digest send failed: %s", exc)
            return 4
        delivered_message_ids = message_ids_safe_to_mark(jobs, digest.included_urls, all_message_ids)
        state.mark_delivered(digest.included_urls, delivered_message_ids)
        LOGGER.info("Sent %s", digest.subject)
        return 0


def main() -> int:
    return run()
