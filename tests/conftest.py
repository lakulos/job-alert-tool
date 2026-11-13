from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from job_alert.config import AppConfig, load_config
from job_alert.models import Job

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


@pytest.fixture
def config() -> AppConfig:
    return load_config(ROOT / "config.yaml")


@pytest.fixture
def make_job():
    def factory(**changes: object) -> Job:
        values = {
            "source": "test",
            "source_id": "1",
            "url": "https://example.com/jobs/1",
            "title": "Senior DevOps Engineer",
            "company": "Example",
            "location": "Remote, worldwide",
            "description": "Remote role. We sponsor visas.",
            "posted_at": NOW,
            "observed_at": NOW,
            "work_mode": "remote",
        }
        values.update(changes)
        return Job(**values)  # type: ignore[arg-type]

    return factory
