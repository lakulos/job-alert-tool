from __future__ import annotations

import httpx
import pytest

from job_alert.http import HttpClient


def test_permanent_client_error_is_not_retried():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(404, request=request)

    with (
        HttpClient(retries=2, transport=httpx.MockTransport(handler)) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        client.get_json("https://example.com/missing")
    assert calls == 1


def test_server_error_is_retried(monkeypatch):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(503 if calls == 1 else 200, json={"ok": True}, request=request)

    monkeypatch.setattr("job_alert.http.time.sleep", lambda _delay: None)
    with HttpClient(retries=2, transport=httpx.MockTransport(handler)) as client:
        assert client.get_json("https://example.com") == {"ok": True}
    assert calls == 2


def test_retry_after_seconds_is_bounded():
    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(429, headers={"Retry-After": "120"}, request=request)
    assert HttpClient._retry_delay(response, 0) == 30
