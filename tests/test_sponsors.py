from __future__ import annotations

from job_alert.filters import assign_tracks
from job_alert.models import Evidence, Sponsorship, Track
from job_alert.sponsors import (
    apply_sponsor_match,
    find_csv_url,
    normalize_company_name,
    parse_sponsor_names,
)


def test_normalized_exact_sponsor_match_is_annotation_only(make_job):
    job = make_job(company="Example Technologies Ltd", sponsorship=Evidence(Sponsorship.UNCLEAR, "none"))
    apply_sponsor_match(job, {normalize_company_name("Example Technologies Limited")})
    assign_tracks(job)
    assert job.sponsorship.value == Sponsorship.LIKELY
    assert Track.VISA_OR_RELOCATION not in job.tracks


def test_sponsor_does_not_override_negative(make_job):
    job = make_job(company="Example Ltd", sponsorship=Evidence(Sponsorship.NONE, "no sponsorship"))
    apply_sponsor_match(job, {normalize_company_name("Example Limited")})
    assert job.sponsorship.value == Sponsorship.NONE


def test_sponsor_csv_and_publication_link():
    csv_text = "Organisation Name,Town/City,County,Type & Rating,Route\nExample Ltd,London,,Worker,Skilled Worker\n"
    assert parse_sponsor_names(csv_text) == {"example"}
    html = '<a href="https://assets.publishing.service.gov.uk/register.csv">CSV</a>'
    assert find_csv_url(html).endswith("register.csv")
