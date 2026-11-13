from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from job_alert.dedupe import canonicalize_url
from job_alert.models import Job, SourceResult, UnparsedAlert


@dataclass(frozen=True, slots=True)
class SenderRule:
    board: str
    senders: frozenset[str]
    allowed_hosts: frozenset[str]
    path_contains: tuple[str, ...]


def sender_rules(
    alert_senders: dict[str, list[str]],
    email_rules: dict[str, dict[str, Any]],
) -> tuple[SenderRule, ...]:
    rules: list[SenderRule] = []
    for board, senders in alert_senders.items():
        configured = email_rules.get(board, {})
        rules.append(
            SenderRule(
                board=board,
                senders=frozenset(address.casefold() for address in senders),
                allowed_hosts=frozenset(
                    str(host).casefold() for host in configured.get("allowed_hosts", [])
                ),
                path_contains=tuple(str(path) for path in configured.get("path_contains", [])),
            )
        )
    return tuple(rules)


def _body(message: EmailMessage) -> str:
    html_part = message.get_body(preferencelist=("html",))
    if html_part:
        return str(html_part.get_content())
    plain = message.get_body(preferencelist=("plain",))
    if plain:
        text = plain.get_content()
        return f"<pre>{text}</pre>"
    return ""


def _date(message: EmailMessage, now: datetime) -> datetime:
    value = message.get("Date")
    if not value:
        return now
    try:
        result = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return now
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _unwrap_link(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    if host.endswith("linkedin.com") and parsed.path.startswith("/comm/"):
        query = parse_qs(parsed.query)
        for key in ("url", "redirect", "redirectUrl"):
            if values := query.get(key):
                return unquote(values[0])
        marker = "/jobs/view/"
        if marker in parsed.path:
            path = marker + parsed.path.split(marker, 1)[1]
            return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))
    return url


def _matches_link(url: str, rule: SenderRule) -> bool:
    parsed = urlsplit(_unwrap_link(url))
    host = (parsed.hostname or "").casefold()
    return host in rule.allowed_hosts and any(token in parsed.path for token in rule.path_contains)


def _card(anchor: Tag) -> Tag:
    fallback = anchor
    for parent in anchor.parents:
        if not isinstance(parent, Tag) or parent.name in {"body", "html", "[document]"}:
            break
        links = parent.select("a[href]")
        text = " ".join(parent.stripped_strings)
        is_explicit_card = parent.name in {"article", "li", "tr"} or "job" in " ".join(
            parent.get("class", [])
        )
        if is_explicit_card and len(text) <= 1200:
            return parent
        if len(links) == 1 and len(text) <= 1200:
            fallback = parent
    return fallback


def _card_fields(anchor: Tag, title: str) -> tuple[str, str, str]:
    card = _card(anchor)
    text = " ".join(card.stripped_strings)
    extras = [value for value in card.stripped_strings if value != title]
    company = extras[0] if extras else ""
    location = extras[1] if len(extras) > 1 else ""
    return company[:200], location[:200], text[:1200]


def parse_alert_message(
    raw: bytes,
    rules: tuple[SenderRule, ...],
    own_address: str,
    now: datetime | None = None,
) -> SourceResult:
    now = now or datetime.now(UTC)
    message = BytesParser(policy=default).parsebytes(raw)
    message_id = str(message.get("Message-ID", "")).strip()
    subject = str(message.get("Subject", "(no subject)"))
    sender = parseaddr(str(message.get("From", "")))[1].casefold()
    received_at = _date(message, now)

    if message.get("X-Job-Digest") == "1" or sender == own_address.casefold():
        return SourceResult(source="gmail_alerts")
    rule = next((candidate for candidate in rules if sender in candidate.senders), None)
    if rule is None:
        return SourceResult(source="gmail_alerts")

    soup = BeautifulSoup(_body(message), "html.parser")
    jobs: list[Job] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        title = " ".join(anchor.stripped_strings)
        if not isinstance(href, str) or not title or not _matches_link(href, rule):
            continue
        url = canonicalize_url(_unwrap_link(href))
        if url in seen:
            continue
        seen.add(url)
        company, location, description = _card_fields(anchor, title)
        jobs.append(
            Job(
                source=f"gmail:{rule.board}",
                source_id=url,
                url=url,
                title=title,
                company=company,
                location=location,
                description=description,
                posted_at=received_at,
                observed_at=now,
                metadata={
                    "message_id": message_id,
                    "email_subject": subject,
                    "date_basis": "alert_received_at",
                },
            )
        )

    result = SourceResult(source="gmail_alerts", jobs=jobs)
    if message_id:
        result.message_ids.add(message_id)
    if not jobs:
        result.unparsed_alerts.append(UnparsedAlert(message_id, subject))
    return result
