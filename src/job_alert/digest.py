from __future__ import annotations

from collections.abc import Iterable
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from job_alert.models import DigestContent, Job, Track, UnparsedAlert


def build_digest(
    jobs: Iterable[Job],
    unparsed_alerts: Iterable[UnparsedAlert],
    max_jobs: int,
) -> DigestContent:
    ordered = sorted(jobs, key=lambda job: job.posted_at, reverse=True)
    # Cap globally by recency; overlapping jobs still render in every applicable section.
    included: dict[str, Job] = {}
    for job in ordered:
        if job.url in included:
            continue
        if len(included) >= max_jobs:
            break
        included[job.url] = job

    selected = list(included.values())
    selected.sort(key=lambda job: job.posted_at, reverse=True)
    return DigestContent(
        remote=[
            job
            for job in selected
            if job.tracks & {Track.REMOTE_WORLDWIDE, Track.REMOTE_EMEA}
        ],
        visa_or_relocation=[job for job in selected if Track.VISA_OR_RELOCATION in job.tracks],
        unparsed_alerts=sorted(
            unparsed_alerts,
            key=lambda alert: alert.subject.casefold(),
        ),
        included_urls=set(included),
    )


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=select_autoescape(("html", "xml")),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_digest(content: DigestContent) -> tuple[str, str]:
    environment = _environment()
    context = {"digest": content}
    html = environment.get_template("digest.html.j2").render(context)
    text = environment.get_template("digest.txt.j2").render(context)
    return html, text


def create_message(
    content: DigestContent,
    sender: str,
    recipient: str,
    html: str,
    text: str,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = content.subject
    message["From"] = sender
    message["To"] = recipient
    message["X-Job-Digest"] = "1"
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    return message
