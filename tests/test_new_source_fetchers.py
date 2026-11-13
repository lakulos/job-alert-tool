from __future__ import annotations

import httpx
from conftest import NOW

from job_alert.http import HttpClient
from job_alert.sources.ats import fetch_recruitee, fetch_smartrecruiters


def test_smartrecruiters_hydrates_posting_details():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/postings"):
            return httpx.Response(
                200,
                json={
                    "totalFound": 1,
                    "content": [
                        {
                            "id": "1",
                            "name": "DevOps Engineer",
                            "releasedDate": NOW.isoformat(),
                            "location": {"remote": True},
                        }
                    ],
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "postingUrl": "https://jobs.smartrecruiters.com/acme/1",
                "jobAd": {"sections": {"jobDescription": {"text": "Remote worldwide"}}},
            },
            request=request,
        )

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        jobs = fetch_smartrecruiters(client, "acme", NOW)
    assert len(requests) == 2
    assert jobs[0].work_mode == "remote" and "Remote worldwide" in jobs[0].description


def test_recruitee_sends_optional_token_header():
    observed = None

    def handler(request):
        nonlocal observed
        observed = request.headers.get("X-Careers-Sites-Token")
        return httpx.Response(200, json={"offers": []}, request=request)

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        assert fetch_recruitee(client, "acme", NOW, "secret-token") == []
    assert observed == "secret-token"
