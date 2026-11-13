from __future__ import annotations

from email.message import EmailMessage

import pytest
from conftest import NOW

from job_alert.email_alerts.imap import fetch_gmail_alerts
from job_alert.email_alerts.parser import parse_alert_message, sender_rules
from job_alert.filters import classify_job
from job_alert.models import RemoteScope, Track


def eml(sender="alerts@wellfound.com", extra_headers=None, html=None):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "me@gmail.com"
    message["Subject"] = "New matching jobs"
    message["Message-ID"] = "<alert-1@example.com>"
    message["Date"] = "Fri, 16 Oct 2026 10:00:00 +0000"
    for name, value in (extra_headers or {}).items():
        message[name] = value
    message.set_content("Job alert")
    message.add_alternative(
        html or '<a href="https://wellfound.com/jobs/123?utm_source=email">Senior DevOps Engineer</a>',
        subtype="html",
    )
    return message.as_bytes()


@pytest.fixture
def rules(config):
    return sender_rules(config.alert_senders, config.email_rules)


def test_parses_allowlisted_anchor(rules):
    result = parse_alert_message(eml(), rules, "me@gmail.com", NOW)
    assert result.jobs[0].title == "Senior DevOps Engineer"
    assert result.jobs[0].url == "https://wellfound.com/jobs/123"


@pytest.mark.parametrize(
    ("board", "sender", "url"),
    [
        ("linkedin", "jobalerts-noreply@linkedin.com", "https://www.linkedin.com/jobs/view/1"),
        ("wellfound", "alerts@wellfound.com", "https://wellfound.com/jobs/1"),
        ("jobberman", "job-alerts@jobberman.com", "https://www.jobberman.com/job/1"),
        ("myjobmag", "jobs@myjobmag.com", "https://www.myjobmag.com/jobs/one"),
        ("hotnigerianjobs", "alerts@hotnigerianjobs.com", "https://www.hotnigerianjobs.com/jobs/1"),
    ],
)
def test_each_sender_rule(rules, board, sender, url):
    result = parse_alert_message(eml(sender, html=f'<a href="{url}">Cloud Engineer</a>'), rules, "me@gmail.com", NOW)
    assert result.jobs[0].source == f"gmail:{board}"


def test_linkedin_card_context_is_available_for_eligibility(rules):
    html = """
    <table><tr class="job-card"><td>
      <a href="https://www.linkedin.com/jobs/view/123?trk=email&amp;utm_source=alert">Senior DevOps Engineer</a>
      <div>Cloud Co</div><div>Remote, worldwide</div>
      <p>Work from anywhere in the world. Visa sponsorship is available.</p>
    </td></tr></table>
    """
    result = parse_alert_message(
        eml("jobalerts-noreply@linkedin.com", html=html), rules, "me@gmail.com", NOW
    )
    job = result.jobs[0]
    assert job.url == "https://www.linkedin.com/jobs/view/123"
    assert job.company == "Cloud Co"
    assert job.location == "Remote, worldwide"
    assert "Visa sponsorship is available" in job.description


def test_compact_multi_job_wrapper_does_not_leak_card_evidence(rules):
    html = """
    <div>
      <a href="https://www.linkedin.com/jobs/view/1">DevOps Engineer</a>
      <span>Remote worldwide</span>
      <a href="https://www.linkedin.com/jobs/view/2">Cloud Engineer</a>
      <span>US only</span>
    </div>
    """
    result = parse_alert_message(
        eml("jobalerts-noreply@linkedin.com", html=html), rules, "me@gmail.com", NOW
    )
    assert [job.description for job in result.jobs] == ["DevOps Engineer", "Cloud Engineer"]


def test_linkedin_emea_card_qualifies_as_remote(rules, config):
    html = """
    <div class="job-card">
      <div><a href="https://www.linkedin.com/jobs/view/456?trk=email">Senior DevOps Engineer</a></div>
      <div>Cloud Co</div><div>EMEA (Remote)</div>
      <p>Fully remote across EMEA.</p>
    </div>
    """
    result = parse_alert_message(
        eml("jobalerts-noreply@linkedin.com", html=html), rules, "me@gmail.com", NOW
    )
    job = classify_job(result.jobs[0], config)
    assert job.source == "gmail:linkedin"
    assert job.remote_scope.value == RemoteScope.EMEA
    assert job.tracks == {Track.REMOTE_EMEA}


def test_linkedin_restricted_card_does_not_get_remote_track(rules, config):
    html = """
    <div class="job-card">
      <a href="https://www.linkedin.com/jobs/view/457">Senior DevOps Engineer</a>
      <div>Cloud Co</div><div>EMEA (Remote)</div>
      <p>Fully remote across EMEA; candidates must be based in Germany.</p>
    </div>
    """
    result = parse_alert_message(
        eml("jobalerts-noreply@linkedin.com", html=html), rules, "me@gmail.com", NOW
    )
    job = classify_job(result.jobs[0], config)
    assert job.remote_scope.value == RemoteScope.RESTRICTED
    assert Track.REMOTE_EMEA not in job.tracks


def test_linkedin_duplicate_links_are_suppressed(rules):
    html = """
    <div class="job-card">
      <a href="https://www.linkedin.com/jobs/view/123?utm_source=one">DevOps Engineer</a>
      <a href="https://www.linkedin.com/jobs/view/123?utm_source=two">DevOps Engineer</a>
    </div>
    """
    result = parse_alert_message(
        eml("jobalerts-noreply@linkedin.com", html=html), rules, "me@gmail.com", NOW
    )
    assert len(result.jobs) == 1


def test_unparsed_subject_is_recorded(rules):
    result = parse_alert_message(eml(html="<p>No recognizable anchors</p>"), rules, "me@gmail.com", NOW)
    assert result.unparsed_alerts[0].subject == "New matching jobs"


def test_ignores_own_digest_header_and_address(rules):
    assert not parse_alert_message(eml(extra_headers={"X-Job-Digest": "1"}), rules, "me@gmail.com", NOW).jobs
    assert not parse_alert_message(eml(sender="me@gmail.com"), rules, "me@gmail.com", NOW).jobs


class FakeImap:
    def __init__(self, _host):
        self.calls = []

    def login(self, *_args):
        self.calls.append("login")

    def select(self, *_args, **kwargs):
        self.calls.append(("select", kwargs))
        return "OK", []

    def search(self, *_args):
        return "OK", [b"1"]

    def fetch(self, sequence, query):
        self.calls.append(("fetch", query))
        return "OK", [(b"meta", eml())]

    def logout(self):
        self.calls.append("logout")


def test_imap_uses_read_only_and_body_peek(rules):
    instances = []

    def factory(host):
        instance = FakeImap(host)
        instances.append(instance)
        return instance

    result = fetch_gmail_alerts("me@gmail.com", "not-a-real-password", rules, set(), NOW, factory)
    assert result.jobs
    assert ("select", {"readonly": True}) in instances[0].calls
    assert ("fetch", "(BODY.PEEK[])") in instances[0].calls
