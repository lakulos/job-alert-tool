from __future__ import annotations

import json

from conftest import FIXTURES, NOW

from job_alert.sources.apify import parse_apify
from job_alert.sources.arbeitnow import parse_arbeitnow
from job_alert.sources.ats import (
    parse_ashby,
    parse_greenhouse,
    parse_lever,
    parse_recruitee,
    parse_smartrecruiters,
)
from job_alert.sources.jooble import parse_jooble
from job_alert.sources.myjobmag import parse_myjobmag
from job_alert.sources.remote import (
    parse_himalayas,
    parse_jobicy,
    parse_remote_ok,
    parse_remotive,
    parse_wwr,
)


def load(name):
    return json.loads((FIXTURES / name).read_text())


def test_greenhouse_parser():
    job = parse_greenhouse(load("greenhouse.json"), "acme", NOW)[0]
    assert job.title == "Senior DevOps Engineer" and job.company == "acme"
    assert job.url == "https://boards.example/jobs/1?utm_source=x"


def test_lever_parser():
    job = parse_lever(load("lever.json"), "acme", NOW)[0]
    assert job.location == "Ikeja, Nigeria" and job.work_mode == "hybrid"
    assert job.url == "https://jobs.example/l1"


def test_ashby_parser():
    job = parse_ashby(load("ashby.json"), "acme", NOW)[0]
    assert job.title == "Site Reliability Engineer" and job.work_mode == "remote"


def test_smartrecruiters_parser_combines_sections():
    job = parse_smartrecruiters(load("smartrecruiters.json"), "example", NOW)[0]
    assert job.company == "Example Cloud" and job.location == "London, GB"
    assert "Visa sponsorship is available" in job.description


def test_recruitee_parser_normalizes_locations():
    job = parse_recruitee(load("recruitee.json"), "example", NOW)[0]
    assert job.location == "Amsterdam, Netherlands"
    assert "Relocation support is provided" in job.description


def test_remotive_parser_has_attribution():
    job = parse_remotive(load("remotive.json"), NOW)[0]
    assert job.metadata["attribution"] == "Remotive"


def test_remote_ok_parser_skips_legal_record():
    jobs = parse_remote_ok(load("remote_ok.json"), NOW)
    assert len(jobs) == 1
    assert jobs[0].source_id == "ro-1" and jobs[0].metadata["attribution"] == "Remote OK"


def test_jobicy_parser():
    job = parse_jobicy(load("jobicy.json"), NOW)[0]
    assert job.title == "Cloud Engineer" and job.metadata["attribution"] == "Jobicy"


def test_himalayas_parser_preserves_restrictions():
    payload = load("himalayas.json")
    payload["jobs"][0]["locationRestrictions"] = ["Canada"]
    payload["jobs"][0]["timezoneRestrictions"] = ["UTC-5"]
    job = parse_himalayas(payload, NOW)[0]
    assert job.location == "Canada, UTC-5"
    assert "Remote within Canada, UTC-5" in job.description


def test_wwr_parser():
    job = parse_wwr((FIXTURES / "wwr.xml").read_text(), NOW)[0]
    assert job.company == "Cloud Co" and job.title == "Cloud Engineer"


def test_arbeitnow_parser_marks_filter():
    job = parse_arbeitnow(load("arbeitnow.json"), NOW)[0]
    assert job.metadata["sponsorship_filtered"] is True


def test_jooble_parser_records_query_track_without_seeding_eligibility():
    job = parse_jooble(load("jooble.json"), NOW, "visa_or_relocation")[0]
    assert job.metadata == {"jooble_track": "visa_or_relocation"}
    assert "sponsorship_filtered" not in job.metadata


def test_myjobmag_parser():
    job = parse_myjobmag((FIXTURES / "myjobmag.xml").read_text(), NOW)[0]
    assert job.title == "DevOps Engineer" and job.company == "Lagos Cloud"


def test_apify_parser():
    job = parse_apify(
        [{"id": "1", "url": "https://example.com/1", "title": "DevOps Engineer", "date": NOW.isoformat()}],
        "example",
        NOW,
    )[0]
    assert job.source == "apify:example"
