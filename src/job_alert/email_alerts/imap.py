from __future__ import annotations

import contextlib
import imaplib
import logging
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta

from job_alert.email_alerts.parser import SenderRule, parse_alert_message
from job_alert.models import SourceResult

LOGGER = logging.getLogger(__name__)


def fetch_gmail_alerts(
    address: str,
    app_password: str,
    rules: tuple[SenderRule, ...],
    processed_message_ids: set[str],
    now: datetime | None = None,
    imap_factory: Callable[[str], imaplib.IMAP4_SSL] = imaplib.IMAP4_SSL,
) -> SourceResult:
    now = now or datetime.now(UTC)
    aggregate = SourceResult(source="gmail_alerts")
    client = imap_factory("imap.gmail.com")
    try:
        client.login(address, app_password)
        status, _ = client.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError("could not open Gmail INBOX read-only")
        since = (now - timedelta(days=7)).strftime("%d-%b-%Y")
        status, data = client.search(None, "SINCE", since)
        if status != "OK":
            raise RuntimeError("Gmail search failed")
        ids: Iterable[bytes] = data[0].split() if data and data[0] else []
        for sequence_bytes in ids:
            sequence = sequence_bytes.decode()
            status, response = client.fetch(sequence, "(BODY.PEEK[])")
            if status != "OK" or not response:
                LOGGER.warning("Could not fetch Gmail message sequence %s", sequence)
                continue
            raw = next(
                (
                    item[1]
                    for item in response
                    if isinstance(item, tuple) and isinstance(item[1], bytes)
                ),
                None,
            )
            if raw is None:
                continue
            parsed = parse_alert_message(raw, rules, address, now)
            if parsed.message_ids & processed_message_ids:
                continue
            aggregate.jobs.extend(parsed.jobs)
            aggregate.unparsed_alerts.extend(parsed.unparsed_alerts)
            aggregate.message_ids.update(parsed.message_ids)
    finally:
        with contextlib.suppress(imaplib.IMAP4.error):
            client.logout()
    return aggregate
