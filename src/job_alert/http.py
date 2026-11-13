from __future__ import annotations

import time
from email.utils import parsedate_to_datetime
from typing import Any

import httpx


class HttpClient:
    def __init__(
        self,
        timeout_seconds: float = 20,
        retries: int = 2,
        user_agent: str = "job-alert/0.1",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.retries = retries
        self.client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept": "application/json, application/xml, text/*"},
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        fallback = float(min(2**attempt, 4))
        if response is None or not (value := response.headers.get("Retry-After")):
            return fallback
        try:
            return min(max(float(value), 0), 30)
        except ValueError:
            try:
                delay = (parsedate_to_datetime(value) - parsedate_to_datetime(response.headers["Date"])).total_seconds()
            except (KeyError, TypeError, ValueError):
                return fallback
            return min(max(delay, 0), 30)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            response: httpx.Response | None = None
            try:
                response = self.client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except httpx.TransportError as exc:
                last = exc
            except httpx.HTTPStatusError as exc:
                last = exc
                if exc.response.status_code != 429 and exc.response.status_code < 500:
                    raise
                response = exc.response
            if attempt >= self.retries:
                raise last
            time.sleep(self._retry_delay(response, attempt))
        raise RuntimeError("unreachable") from last

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self.request("GET", url, **kwargs).json()

    def post_json(self, url: str, **kwargs: Any) -> Any:
        return self.request("POST", url, **kwargs).json()

    def get_text(self, url: str, **kwargs: Any) -> str:
        return self.request("GET", url, **kwargs).text
