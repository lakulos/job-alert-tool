from __future__ import annotations

from conftest import NOW

from job_alert.dedupe import canonicalize_url, merge_jobs
from job_alert.digest import build_digest, create_message, render_digest
from job_alert.models import Track, UnparsedAlert
from job_alert.state import StateStore


def test_url_canonicalization():
    assert canonicalize_url("HTTPS://Example.COM:443/jobs/1/?utm_source=x&b=2#top") == "https://example.com/jobs/1?b=2"
    assert (
        canonicalize_url("https://www.linkedin.com/jobs/view/123?trk=email&trackingId=x&refId=y")
        == "https://www.linkedin.com/jobs/view/123"
    )


def test_merge_tracks(make_job):
    from job_alert.models import Evidence, Sponsorship

    left = make_job(url="https://example.com/jobs/1?utm_source=a", tracks={Track.REMOTE_WORLDWIDE})
    right = make_job(
        url="https://example.com/jobs/1",
        tracks={Track.VISA_OR_RELOCATION},
        sponsorship=Evidence(Sponsorship.EXPLICIT, "visa sponsorship available"),
    )
    merged = merge_jobs([left, right])
    assert merged[0].tracks == {Track.REMOTE_WORLDWIDE, Track.VISA_OR_RELOCATION}


def test_merge_removes_track_when_stronger_evidence_is_negative(make_job):
    from job_alert.models import Evidence, RemoteScope, Sponsorship

    positive = make_job(
        url="https://example.com/jobs/1",
        tracks={Track.REMOTE_WORLDWIDE, Track.VISA_OR_RELOCATION},
        sponsorship=Evidence(Sponsorship.EXPLICIT, "visa sponsorship available"),
    )
    negative = make_job(
        url="https://example.com/jobs/1?utm_source=x",
        remote_scope=Evidence(RemoteScope.RESTRICTED, "US only"),
        sponsorship=Evidence(Sponsorship.NONE, "no sponsorship"),
    )
    merged = merge_jobs([positive, negative])[0]
    assert Track.REMOTE_WORLDWIDE not in merged.tracks
    assert Track.VISA_OR_RELOCATION not in merged.tracks


def test_merge_preserves_visa_when_only_relocation_is_negative(make_job):
    from job_alert.models import Evidence, Sponsorship

    sponsored = make_job(
        url="https://example.com/jobs/1",
        tracks={Track.VISA_OR_RELOCATION},
        sponsorship=Evidence(Sponsorship.EXPLICIT, "visa sponsorship available"),
    )
    no_relocation = make_job(
        url="https://example.com/jobs/1?utm_source=x",
        relocation=Evidence(Sponsorship.NONE, "no relocation assistance"),
    )
    assert Track.VISA_OR_RELOCATION in merge_jobs([sponsored, no_relocation])[0].tracks


def test_global_cap_and_overlap(make_job):
    from datetime import timedelta

    overlap = make_job(
        url="https://example.com/1",
        posted_at=NOW - timedelta(hours=1),
        tracks={Track.REMOTE_WORLDWIDE, Track.VISA_OR_RELOCATION},
    )
    visa = make_job(url="https://example.com/2", tracks={Track.VISA_OR_RELOCATION})
    content = build_digest([overlap, visa], [], 1)
    assert content.unique_job_count == 1
    assert content.visa_or_relocation == [visa]
    assert not content.remote


def test_overlap_renders_in_each_section(make_job):
    overlap = make_job(
        url="https://example.com/1",
        tracks={Track.REMOTE_WORLDWIDE, Track.VISA_OR_RELOCATION},
    )
    content = build_digest([overlap], [], 1)
    assert content.remote == [overlap] and content.visa_or_relocation == [overlap]


def test_message_headers_and_alternatives(make_job):
    job = make_job(tracks={Track.REMOTE_WORLDWIDE})
    content = build_digest([job], [], 10)
    html, text = render_digest(content)
    message = create_message(content, "me@gmail.com", "to@gmail.com", html, text)
    assert message["X-Job-Digest"] == "1"
    assert message["Subject"] == "Job alerts (1): 1 remote anywhere, 0 visa/relocation"
    assert "Nigeria" not in html
    assert message.is_multipart()


def test_unparsed_only_digest():
    content = build_digest([], [UnparsedAlert("<1>", "Broken alert")], 10)
    assert content.has_content and content.subject.startswith("Job alerts (0):")


def test_state_marks_atomically(tmp_path):
    with StateStore(tmp_path / "state.sqlite3") as state:
        assert not state.sent_urls()
        state.mark_delivered(["https://example.com/1"], ["<message-1>"])
        assert state.sent_urls() == {"https://example.com/1"}
        assert state.processed_message_ids() == {"<message-1>"}
