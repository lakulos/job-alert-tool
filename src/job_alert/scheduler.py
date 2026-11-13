from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from datetime import time as clock_time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LOGGER = logging.getLogger(__name__)
DEFAULT_TIMES = "07:07,19:07"
DEFAULT_TIMEZONE = "Africa/Lagos"


def parse_times(value: str) -> tuple[clock_time, ...]:
    parsed: set[clock_time] = set()
    for raw in value.split(","):
        item = raw.strip()
        try:
            hour_text, minute_text = item.split(":", 1)
            scheduled = clock_time(hour=int(hour_text), minute=int(minute_text))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid scheduled time {item!r}; expected HH:MM") from exc
        parsed.add(scheduled)
    if not parsed:
        raise ValueError("at least one scheduled time is required")
    return tuple(sorted(parsed))


def next_run(now: datetime, scheduled_times: tuple[clock_time, ...]) -> datetime:
    if now.tzinfo is None:
        raise ValueError("scheduler clock must be timezone-aware")
    for scheduled in scheduled_times:
        candidate = datetime.combine(now.date(), scheduled, now.tzinfo)
        if candidate > now:
            return candidate
    return datetime.combine(now.date() + timedelta(days=1), scheduled_times[0], now.tzinfo)


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def run_job(config_path: Path) -> int:
    command = [sys.executable, "-m", "job_alert", "--config", str(config_path)]
    LOGGER.info("Starting scheduled job-alert run")
    completed = subprocess.run(command, check=False)
    if completed.returncode:
        LOGGER.error("Scheduled job-alert run exited with status %d", completed.returncode)
    else:
        LOGGER.info("Scheduled job-alert run completed")
    return completed.returncode


def write_health(path: Path, status: str, when: datetime, return_code: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [f"status={status}", f"at={when.isoformat()}"]
    if return_code is not None:
        fields.append(f"return_code={return_code}")
    path.write_text("\n".join(fields) + "\n", encoding="utf-8")


def scheduler_loop(
    config_path: Path,
    scheduled_times: tuple[clock_time, ...],
    timezone: ZoneInfo,
    run_on_start: bool,
    health_path: Path,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    runner: Callable[[Path], int] = run_job,
    should_stop: Callable[[], bool] | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    now_fn = now_fn or (lambda: datetime.now(timezone))
    should_stop = should_stop or (lambda: False)
    write_health(health_path, "ready", now_fn())

    if run_on_start and not should_stop():
        code = runner(config_path)
        write_health(health_path, "ok" if code == 0 else "error", now_fn(), code)

    while not should_stop():
        now = now_fn()
        target = next_run(now, scheduled_times)
        delay = max(0.0, (target - now).total_seconds())
        LOGGER.info("Next job-alert run: %s", target.isoformat())
        remaining = delay
        while remaining > 0 and not should_stop():
            interval = min(remaining, 60.0)
            if stop_event is not None:
                stop_event.wait(interval)
            else:
                sleep_fn(interval)
            remaining -= interval
        if should_stop():
            break
        code = runner(config_path)
        write_health(health_path, "ok" if code == 0 else "error", now_fn(), code)


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        timezone = ZoneInfo(os.getenv("JOB_ALERT_TIMEZONE", DEFAULT_TIMEZONE))
        scheduled_times = parse_times(os.getenv("JOB_ALERT_TIMES", DEFAULT_TIMES))
        run_on_start = env_flag("RUN_ON_START", True)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        LOGGER.error("Invalid scheduler configuration: %s", exc)
        return 2

    stop_event = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()
        LOGGER.info("Shutdown requested")

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    scheduler_loop(
        config_path=Path(os.getenv("JOB_ALERT_CONFIG", "/app/config.yaml")),
        scheduled_times=scheduled_times,
        timezone=timezone,
        run_on_start=run_on_start,
        health_path=Path(os.getenv("JOB_ALERT_HEALTH_FILE", "/app/.cache/job-alert/health")),
        should_stop=stop_event.is_set,
        stop_event=stop_event,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
