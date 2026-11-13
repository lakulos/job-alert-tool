from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import NOW

from job_alert.classifiers import classify_relocation, classify_remote, classify_sponsorship
from job_alert.filters import classify_job, is_fresh, title_is_allowed
from job_alert.models import RemoteScope, Sponsorship, Track


def test_title_rules(config):
    assert title_is_allowed("Senior DevOps Engineer", config)
    assert not title_is_allowed("Marketing Manager", config)
    assert not title_is_allowed("Cloud Engineer Intern", config)


@pytest.mark.parametrize(
    "text",
    [
        "Remote (US only)",
        "Remote within India only; worldwide team",
        "Candidates anywhere in the US may apply",
        "Remote role for EMEA",
        "Remote role for Africa",
        "Remote worldwide; must reside in Canada",
        "Work from anywhere; must work hours aligned in US Eastern timezone",
    ],
)
def test_remote_rules_reject_restricted_or_ambiguous_scope(text):
    assert classify_remote(text).value != RemoteScope.WORLDWIDE


@pytest.mark.parametrize(
    "text",
    [
        "Remote, worldwide",
        "Work from anywhere in the world",
        "Open to candidates globally for this remote role",
    ],
)
def test_remote_rules_accept_explicit_worldwide_scope(text):
    assert classify_remote(text).value == RemoteScope.WORLDWIDE


def test_global_without_remote_mode_is_not_worldwide_remote():
    assert classify_remote("We are a global team working on-site").value == RemoteScope.UNCLEAR


def test_sponsorship_rules_negative_precedes_positive():
    assert classify_sponsorship("No visa sponsorship; visa sponsorship discussed").value == Sponsorship.NONE
    assert classify_sponsorship("Not eligible for visa sponsorship").value == Sponsorship.NONE
    assert classify_sponsorship("Sponsorship is not available").value == Sponsorship.NONE
    positive = classify_sponsorship("We sponsor visas for this role")
    assert positive.value == Sponsorship.EXPLICIT
    assert positive.phrase.casefold() == "we sponsor visas"


@pytest.mark.parametrize(
    "text",
    [
        "Relocation assistance provided",
        "Relocation package included",
        "Relocation support is available",
        "We will relocate successful candidates",
        "Company-sponsored work permit",
    ],
)
def test_relocation_rules_are_explicit(text):
    assert classify_relocation(text).value == Sponsorship.EXPLICIT


def test_relocation_negative_does_not_hide_explicit_visa_sponsorship():
    text = "No relocation assistance, but visa sponsorship is available"
    assert classify_relocation(text).value == Sponsorship.NONE
    assert classify_sponsorship(text).value == Sponsorship.EXPLICIT


def test_questions_and_conditional_language_do_not_count_as_offers():
    text = "Will you require visa sponsorship? Relocation assistance may be considered."
    assert classify_sponsorship(text).value == Sponsorship.UNCLEAR
    assert classify_relocation(text).value == Sponsorship.UNCLEAR


def test_classifier_only_assigns_strict_tracks(config, make_job):
    unclear = make_job(description="Remote role", location="Remote")
    classify_job(unclear, config)
    assert not unclear.tracks

    worldwide = make_job(description="Remote role", location="Remote, worldwide")
    classify_job(worldwide, config)
    assert worldwide.tracks == {Track.REMOTE_WORLDWIDE}

    sponsored = make_job(description="Visa sponsorship is available", location="London")
    classify_job(sponsored, config)
    assert sponsored.tracks == {Track.VISA_OR_RELOCATION}

    relocated = make_job(description="Relocation support is available", location="Berlin")
    classify_job(relocated, config)
    assert relocated.tracks == {Track.VISA_OR_RELOCATION}


def test_trusted_source_filter_seeds_sponsorship(config, make_job):
    job = make_job(
        description="No decisive eligibility text",
        location="Berlin",
        work_mode="",
        metadata={"sponsorship_filtered": True},
    )
    classify_job(job, config)
    assert job.sponsorship.value == Sponsorship.EXPLICIT
    assert job.tracks == {Track.VISA_OR_RELOCATION}


def test_jooble_query_metadata_does_not_seed_sponsorship(config, make_job):
    job = make_job(
        description="No decisive eligibility text",
        location="Berlin",
        work_mode="",
        metadata={"jooble_track": "visa_or_relocation"},
    )
    classify_job(job, config)
    assert job.sponsorship.value == Sponsorship.UNCLEAR
    assert not job.tracks


def test_freshness_boundary(make_job):
    assert is_fresh(make_job(posted_at=NOW - timedelta(hours=48)), NOW, 48)
    assert not is_fresh(make_job(posted_at=NOW - timedelta(hours=48, seconds=1)), NOW, 48)
