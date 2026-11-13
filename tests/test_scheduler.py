from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from job_alert.scheduler import next_run, parse_times, scheduler_loop

LAGOS = ZoneInfo("Africa/Lagos")


def test_parse_times_sorts_and_deduplicates():
    assert parse_times("19:07, 07:07,19:07") == (time(7, 7), time(19, 7))


def test_parse_times_rejects_invalid_value():
    with pytest.raises(ValueError, match="expected HH:MM"):
        parse_times("25:00")


def test_next_run_same_day():
    now = datetime(2026, 10, 16, 8, tzinfo=LAGOS)
    assert next_run(now, (time(7, 7), time(19, 7))) == datetime(
        2026, 10, 16, 19, 7, tzinfo=LAGOS
    )


def test_next_run_rolls_to_tomorrow():
    now = datetime(2026, 10, 16, 20, tzinfo=LAGOS)
    assert next_run(now, (time(7, 7), time(19, 7))) == datetime(
        2026, 10, 17, 7, 7, tzinfo=LAGOS
    )


def test_scheduler_runs_on_start_and_stops(tmp_path: Path):
    calls: list[Path] = []
    clock_values = iter(
        [
            datetime(2026, 10, 16, 6, tzinfo=LAGOS),
            datetime(2026, 10, 16, 6, tzinfo=LAGOS),
        ]
    )

    scheduler_loop(
        config_path=Path("/app/config.yaml"),
        scheduled_times=(time(7, 7), time(19, 7)),
        timezone=LAGOS,
        run_on_start=True,
        health_path=tmp_path / "health",
        now_fn=lambda: next(clock_values),
        runner=lambda path: calls.append(path) or 0,
        should_stop=lambda: bool(calls),
    )

    assert calls == [Path("/app/config.yaml")]
    assert "status=ok" in (tmp_path / "health").read_text()
