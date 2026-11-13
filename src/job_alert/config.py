from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml


class ConfigError(ValueError):
    """Raised when config.yaml is invalid."""


_SOURCE_IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class HttpConfig:
    timeout_seconds: float
    retries: int
    user_agent: str


@dataclass(frozen=True, slots=True)
class LinkValidationConfig:
    enabled: bool
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class AppConfig:
    path: Path
    raw: dict[str, Any]
    title_patterns: tuple[re.Pattern[str], ...]
    exclude_title_terms: tuple[str, ...]
    lagos_aliases: tuple[str, ...]
    max_jobs_per_email: int
    freshness_hours: int
    state_path: Path
    cache_dir: Path
    http: HttpConfig
    link_validation: LinkValidationConfig

    @property
    def sources(self) -> dict[str, dict[str, Any]]:
        return cast(dict[str, dict[str, Any]], self.raw["sources"])

    @property
    def alert_senders(self) -> dict[str, list[str]]:
        return cast(dict[str, list[str]], self.raw.get("alert_senders", {}))

    @property
    def email_rules(self) -> dict[str, dict[str, Any]]:
        return cast(dict[str, dict[str, Any]], self.raw.get("email_rules", {}))


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot load {config_path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigError("config must be a YAML mapping")

    roles = loaded.get("roles")
    if not isinstance(roles, dict):
        raise ConfigError("roles must be configured")
    patterns = roles.get("title_patterns")
    if not isinstance(patterns, list) or not patterns:
        raise ConfigError("roles.title_patterns must be a non-empty list")
    try:
        compiled = tuple(re.compile(str(item)) for item in patterns)
    except re.error as exc:
        raise ConfigError(f"invalid title pattern: {exc}") from exc

    base = config_path.parent
    try:
        max_jobs = int(loaded.get("max_jobs_per_email", 50))
        freshness = int(loaded.get("freshness_hours", 48))
    except (TypeError, ValueError) as exc:
        raise ConfigError("max_jobs_per_email and freshness_hours must be integers") from exc
    if max_jobs < 1 or freshness < 1:
        raise ConfigError("max_jobs_per_email and freshness_hours must be positive")

    http_raw = loaded.get("http", {})
    if not isinstance(http_raw, dict):
        raise ConfigError("http must be a mapping")
    link_validation_raw = loaded.get("link_validation", {})
    if not isinstance(link_validation_raw, dict):
        raise ConfigError("link_validation must be a mapping")
    try:
        link_timeout = float(link_validation_raw.get("timeout_seconds", 8))
    except (TypeError, ValueError) as exc:
        raise ConfigError("link_validation.timeout_seconds must be a number") from exc
    if not math.isfinite(link_timeout) or link_timeout <= 0:
        raise ConfigError("link_validation.timeout_seconds must be a finite positive number")
    link_enabled = link_validation_raw.get("enabled", True)
    if not isinstance(link_enabled, bool):
        raise ConfigError("link_validation.enabled must be true or false")
    sources = loaded.get("sources")
    if not isinstance(sources, dict):
        raise ConfigError("sources must be a mapping")
    for source_name, key in (("smartrecruiters", "companies"), ("recruitee", "tenants")):
        source = sources.get(source_name, {})
        if not isinstance(source, dict):
            raise ConfigError(f"sources.{source_name} must be a mapping")
        entries = source.get(key, [])
        if not isinstance(entries, list):
            raise ConfigError(f"sources.{source_name}.{key} must be a list")
        for entry in entries:
            identifier = entry.get("slug", "") if isinstance(entry, dict) else entry
            if not isinstance(identifier, str) or not _SOURCE_IDENTIFIER.fullmatch(identifier):
                raise ConfigError(f"invalid sources.{source_name}.{key} identifier")

    return AppConfig(
        path=config_path,
        raw=loaded,
        title_patterns=compiled,
        exclude_title_terms=tuple(
            str(item).strip().casefold() for item in roles.get("exclude_title_terms", [])
        ),
        lagos_aliases=tuple(str(item).strip() for item in loaded.get("lagos_aliases", [])),
        max_jobs_per_email=max_jobs,
        freshness_hours=freshness,
        state_path=_resolve(base, str(loaded.get("state_path", ".cache/job-alert/state.sqlite3"))),
        cache_dir=_resolve(base, str(loaded.get("cache_dir", ".cache/job-alert"))),
        http=HttpConfig(
            timeout_seconds=float(http_raw.get("timeout_seconds", 20)),
            retries=int(http_raw.get("retries", 2)),
            user_agent=str(http_raw.get("user_agent", "job-alert/0.1")),
        ),
        link_validation=LinkValidationConfig(
            enabled=link_enabled,
            timeout_seconds=link_timeout,
        ),
    )
