from __future__ import annotations

import shutil

from conftest import FIXTURES, ROOT

from job_alert.cli import message_ids_safe_to_mark, run
from job_alert.models import Track


def test_fixture_dry_run_needs_no_credentials(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    shutil.copy(ROOT / "config.yaml", config)
    for name in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "DIGEST_TO", "APIFY_TOKEN", "JOOBLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert run(["--config", str(config), "--dry-run", "--fixtures", str(FIXTURES)]) == 0
    output = tmp_path / "digest.html"
    assert output.exists()
    assert "Senior DevOps Engineer" in output.read_text()


def test_message_id_not_marked_when_one_email_job_overflows_cap(make_job):
    included = make_job(
        url="https://example.com/1",
        tracks={Track.REMOTE_WORLDWIDE},
        metadata={"message_id": "<alert-1>"},
    )
    omitted = make_job(
        url="https://example.com/2",
        tracks={Track.REMOTE_WORLDWIDE},
        metadata={"message_id": "<alert-1>"},
    )
    safe = message_ids_safe_to_mark(
        [included, omitted], {included.url}, {"<alert-1>"}
    )
    assert safe == set()
