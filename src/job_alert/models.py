from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class Track(StrEnum):
    REMOTE_WORLDWIDE = "remote_worldwide"
    VISA_OR_RELOCATION = "visa_or_relocation"


class RemoteScope(StrEnum):
    WORLDWIDE = "worldwide"
    RESTRICTED = "restricted"
    UNCLEAR = "unclear"


class Sponsorship(StrEnum):
    EXPLICIT = "explicit"
    LIKELY = "likely"
    NONE = "none"
    UNCLEAR = "unclear"


@dataclass(frozen=True, slots=True)
class Evidence:
    value: str
    phrase: str


@dataclass(slots=True)
class Job:
    source: str
    source_id: str
    url: str
    title: str
    company: str
    location: str
    description: str
    posted_at: datetime
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    work_mode: str = ""
    tracks: set[Track] = field(default_factory=set)
    remote_scope: Evidence = field(
        default_factory=lambda: Evidence(RemoteScope.UNCLEAR, "no decisive phrase found")
    )
    sponsorship: Evidence = field(
        default_factory=lambda: Evidence(Sponsorship.UNCLEAR, "no decisive phrase found")
    )
    relocation: Evidence = field(
        default_factory=lambda: Evidence(Sponsorship.UNCLEAR, "no decisive phrase found")
    )
    nigeria_note: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.posted_at.tzinfo is None or self.observed_at.tzinfo is None:
            raise ValueError("job timestamps must be timezone-aware")
        self.posted_at = self.posted_at.astimezone(UTC)
        self.observed_at = self.observed_at.astimezone(UTC)

    @property
    def searchable_text(self) -> str:
        return " ".join(
            part for part in (self.title, self.location, self.work_mode, self.description) if part
        )

    def copy(self, **changes: Any) -> Job:
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class UnparsedAlert:
    message_id: str
    subject: str


@dataclass(slots=True)
class SourceResult:
    source: str
    jobs: list[Job] = field(default_factory=list)
    unparsed_alerts: list[UnparsedAlert] = field(default_factory=list)
    message_ids: set[str] = field(default_factory=set)
    error: str | None = None


@dataclass(slots=True)
class DigestContent:
    remote: list[Job] = field(default_factory=list)
    visa_or_relocation: list[Job] = field(default_factory=list)
    unparsed_alerts: list[UnparsedAlert] = field(default_factory=list)
    included_urls: set[str] = field(default_factory=set)

    @property
    def unique_job_count(self) -> int:
        return len(self.included_urls)

    @property
    def has_content(self) -> bool:
        return bool(self.included_urls or self.unparsed_alerts)

    @property
    def subject(self) -> str:
        return (
            f"Job alerts ({self.unique_job_count}): {len(self.remote)} remote anywhere, "
            f"{len(self.visa_or_relocation)} visa/relocation"
        )
