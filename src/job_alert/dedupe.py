from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_alert.models import Evidence, Job, RemoteScope, Sponsorship, Track

_TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "refid",
    "source",
    "trackingid",
    "trk",
}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.casefold() or "https"
    host = (parts.hostname or "").casefold()
    port = parts.port
    netloc = host
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc = f"{host}:{port}"
    path = parts.path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_KEYS
        )
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def _stronger_remote(left: Evidence, right: Evidence) -> Evidence:
    rank = {RemoteScope.UNCLEAR: 0, RemoteScope.WORLDWIDE: 1, RemoteScope.RESTRICTED: 2}
    return right if rank[RemoteScope(right.value)] > rank[RemoteScope(left.value)] else left


def _stronger_sponsorship(left: Evidence, right: Evidence) -> Evidence:
    rank = {
        Sponsorship.UNCLEAR: 0,
        Sponsorship.LIKELY: 1,
        Sponsorship.EXPLICIT: 2,
        Sponsorship.NONE: 3,
    }
    return right if rank[Sponsorship(right.value)] > rank[Sponsorship(left.value)] else left


def merge_jobs(jobs: list[Job]) -> list[Job]:
    merged: dict[str, Job] = {}
    for job in jobs:
        job.url = canonicalize_url(job.url)
        current = merged.get(job.url)
        if current is None:
            merged[job.url] = job
            continue
        current.tracks.update(job.tracks)
        current.remote_scope = _stronger_remote(current.remote_scope, job.remote_scope)
        current.sponsorship = _stronger_sponsorship(current.sponsorship, job.sponsorship)
        current.relocation = _stronger_sponsorship(current.relocation, job.relocation)
        if job.posted_at > current.posted_at:
            current.posted_at = job.posted_at
        if job.nigeria_note and not current.nigeria_note:
            current.nigeria_note = job.nigeria_note
        sources = set(current.metadata.get("sources", [current.source]))
        sources.update(job.metadata.get("sources", [job.source]))
        attributions = set(current.metadata.get("attributions", []))
        for candidate in (current.metadata.get("attribution"), job.metadata.get("attribution")):
            if candidate:
                attributions.add(str(candidate))
        attributions.update(str(value) for value in job.metadata.get("attributions", []))
        if attributions:
            current.metadata["attributions"] = sorted(attributions)
        message_ids = set(current.metadata.get("message_ids", []))
        for candidate in (current.metadata.get("message_id"), job.metadata.get("message_id")):
            if candidate:
                message_ids.add(candidate)
        message_ids.update(job.metadata.get("message_ids", []))
        if message_ids:
            current.metadata["message_ids"] = sorted(message_ids)
        current.metadata["sources"] = sorted(sources)
    for job in merged.values():
        if job.remote_scope.value == RemoteScope.RESTRICTED:
            job.tracks.discard(Track.REMOTE_WORLDWIDE)
        if (
            job.sponsorship.value != Sponsorship.EXPLICIT
            and job.relocation.value != Sponsorship.EXPLICIT
        ):
            job.tracks.discard(Track.VISA_OR_RELOCATION)
    return list(merged.values())
