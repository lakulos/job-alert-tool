from __future__ import annotations

import re
from datetime import datetime, timedelta

from job_alert.classifiers import classify_relocation, classify_remote, classify_sponsorship
from job_alert.config import AppConfig
from job_alert.models import Evidence, Job, RemoteScope, Sponsorship, Track


def title_is_allowed(title: str, config: AppConfig) -> bool:
    for term in config.exclude_title_terms:
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", title, re.IGNORECASE):
            return False
    return any(pattern.search(title) for pattern in config.title_patterns)


def is_fresh(job: Job, now: datetime, hours: int) -> bool:
    age = now - job.posted_at
    return timedelta(0) <= age <= timedelta(hours=hours)


def assign_tracks(job: Job) -> Job:
    job.tracks.clear()
    if job.remote_scope.value == RemoteScope.WORLDWIDE:
        job.tracks.add(Track.REMOTE_WORLDWIDE)
    elif job.remote_scope.value == RemoteScope.EMEA:
        job.tracks.add(Track.REMOTE_EMEA)
    if Sponsorship.EXPLICIT in {job.sponsorship.value, job.relocation.value}:
        job.tracks.add(Track.VISA_OR_RELOCATION)
    return job


def classify_job(job: Job, config: AppConfig) -> Job:
    del config  # Reserved for future configurable eligibility policies.
    text = job.searchable_text
    job.remote_scope = classify_remote(text)
    job.sponsorship = classify_sponsorship(text)
    job.relocation = classify_relocation(text)
    if job.metadata.get("sponsorship_filtered") and job.sponsorship.value == Sponsorship.UNCLEAR:
        job.sponsorship = Evidence(Sponsorship.EXPLICIT, "source visa_sponsorship=true filter")
    return assign_tracks(job)
