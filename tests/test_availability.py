from __future__ import annotations

import queue
from datetime import timedelta

import httpx
import pytest
from conftest import NOW

from job_alert.availability import LinkStatus, check_job_link, valid_job_url
from job_alert.http import HttpClient
from job_alert.models import SourceResult
from job_alert.pipeline import filter_and_classify


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(
        "job_alert.availability.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )


@pytest.mark.parametrize(
    "url",
    [
        "job-id-only",
        "ftp://example.com/jobs/1",
        "https:///jobs/1",
        "https://example.com:bad/jobs/1",
    ],
)
def test_invalid_job_urls_are_rejected(make_job, url):
    job = make_job(url=url)
    with HttpClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))) as http:
        assert not valid_job_url(url)
        assert check_job_link(job, http, NOW, 1).status == LinkStatus.UNAVAILABLE


def test_structured_expiration_is_checked_without_network(make_job):
    job = make_job(metadata={"expiry_date": (NOW - timedelta(seconds=1)).isoformat()})

    def unexpected_request(request):
        raise AssertionError(f"unexpected request to {request.url}")

    with HttpClient(transport=httpx.MockTransport(unexpected_request)) as http:
        check = check_job_link(job, http, NOW, 1)
    assert check.status == LinkStatus.UNAVAILABLE
    assert check.reason == "expired according to expiry_date"


def test_invalid_expiration_metadata_fails_open(make_job):
    job = make_job(metadata={"close_at": "not a date"})
    with HttpClient(transport=httpx.MockTransport(lambda request: httpx.Response(204, request=request))) as http:
        check = check_job_link(job, http, NOW, 1)
    assert check.status == LinkStatus.AVAILABLE


def test_head_redirect_is_available(make_job):
    def handler(request):
        if request.url.path == "/jobs/1":
            return httpx.Response(302, headers={"Location": "/open/1"}, request=request)
        return httpx.Response(200, request=request)

    with HttpClient(transport=httpx.MockTransport(handler)) as http:
        check = check_job_link(make_job(), http, NOW, 1)
    assert check.status == LinkStatus.AVAILABLE
    assert check.reason == "HTTP 200"


@pytest.mark.parametrize("status", [404, 410])
def test_definitive_missing_get_is_unavailable(make_job, status):
    methods: list[str] = []

    def handler(request):
        methods.append(request.method)
        return httpx.Response(status, request=request)

    with HttpClient(transport=httpx.MockTransport(handler)) as http:
        check = check_job_link(make_job(), http, NOW, 1)
    assert check.status == LinkStatus.UNAVAILABLE
    assert methods == ["HEAD", "GET"]


@pytest.mark.parametrize("head_status", [403, 405, 501])
def test_rejected_head_falls_back_to_bounded_get(make_job, head_status):
    requests: list[httpx.Request] = []

    def handler(request):
        requests.append(request)
        status = head_status if request.method == "HEAD" else 200
        return httpx.Response(status, request=request)

    with HttpClient(transport=httpx.MockTransport(handler)) as http:
        check = check_job_link(make_job(), http, NOW, 1)
    assert check.status == LinkStatus.AVAILABLE
    assert [request.method for request in requests] == ["HEAD", "GET"]
    assert requests[1].headers["Range"] == "bytes=0-0"


@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_inconclusive_http_status_fails_open(make_job, status):
    with HttpClient(transport=httpx.MockTransport(lambda request: httpx.Response(status, request=request))) as http:
        check = check_job_link(make_job(), http, NOW, 1)
    assert check.status == LinkStatus.UNKNOWN


def test_head_and_get_forbidden_is_inconclusive(make_job):
    with HttpClient(transport=httpx.MockTransport(lambda request: httpx.Response(403, request=request))) as http:
        check = check_job_link(make_job(), http, NOW, 1)
    assert check.status == LinkStatus.UNKNOWN


def test_transport_error_fails_open(make_job):
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    with HttpClient(transport=httpx.MockTransport(handler)) as http:
        check = check_job_link(make_job(), http, NOW, 1)
    assert check.status == LinkStatus.UNKNOWN


def test_non_public_target_is_not_requested(make_job):
    requested = False

    def handler(request):
        nonlocal requested
        requested = True
        return httpx.Response(200, request=request)

    with HttpClient(transport=httpx.MockTransport(handler)) as http:
        check = check_job_link(make_job(url="http://127.0.0.1/jobs/1"), http, NOW, 1)
    assert check.status == LinkStatus.UNKNOWN
    assert not requested


def test_redirect_to_non_public_target_is_not_followed(make_job):
    requests: list[str] = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest"}, request=request)

    with HttpClient(transport=httpx.MockTransport(handler)) as http:
        check = check_job_link(make_job(), http, NOW, 1)
    assert check.status == LinkStatus.UNKNOWN
    assert requests == ["https://93.184.216.34/jobs/1"]


def test_malformed_hostname_fails_open_without_request(make_job):
    requested = False

    def handler(request):
        nonlocal requested
        requested = True
        return httpx.Response(200, request=request)

    with HttpClient(transport=httpx.MockTransport(handler)) as http:
        check = check_job_link(make_job(url="https://exa mple.com/jobs/1"), http, NOW, 1)
    assert check.status == LinkStatus.UNAVAILABLE
    assert not requested


def test_dns_timeout_fails_open_without_request(make_job, monkeypatch):
    class EmptyResults:
        def get(self, timeout):
            raise queue.Empty

        def put(self, value):
            pass

    monkeypatch.setattr("job_alert.availability.queue.Queue", lambda maxsize: EmptyResults())
    requested = False

    def handler(request):
        nonlocal requested
        requested = True
        return httpx.Response(200, request=request)

    with HttpClient(transport=httpx.MockTransport(handler)) as http:
        check = check_job_link(make_job(), http, NOW, 0.01)
    assert check.status == LinkStatus.UNKNOWN
    assert not requested


def test_pipeline_only_probes_eligible_unsent_jobs(config, make_job):
    requested_paths: list[str] = []

    def handler(request):
        requested_paths.append(request.url.path)
        status = 404 if request.url.path == "/jobs/dead" else 200
        return httpx.Response(status, request=request)

    jobs = [
        make_job(source_id="live", url="https://example.com/jobs/live"),
        make_job(source_id="dead", url="https://example.com/jobs/dead"),
        make_job(source_id="irrelevant", url="https://example.com/jobs/irrelevant", title="Accountant"),
        make_job(source_id="sent", url="https://example.com/jobs/sent"),
    ]
    with HttpClient(transport=httpx.MockTransport(handler)) as http:
        selected = filter_and_classify(
            [SourceResult(source="test", jobs=jobs)],
            config,
            {"https://example.com/jobs/sent"},
            http,
            now=NOW,
            use_sponsor_register=False,
        )

    assert [job.source_id for job in selected] == ["live"]
    assert requested_paths == ["/jobs/live", "/jobs/dead", "/jobs/dead"]
