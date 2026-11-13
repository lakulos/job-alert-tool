from __future__ import annotations

import re
from collections.abc import Iterable

from job_alert.models import Evidence, RemoteScope, Sponsorship

_REMOTE_RESTRICTED = (
    re.compile(r"(?i)\b(?:US|USA|UK|Canada|India|Europe|Africa|EMEA|APAC|LATAM)\s+only\b"),
    re.compile(r"(?i)\bremote\s+(?:within|from|in)\s+(?!the\s+world\b)[^.;\n]{2,80}"),
    re.compile(r"(?i)\banywhere\s+in\s+(?!the\s+world\b)[^.;\n]{2,80}"),
    re.compile(r"(?i)\bmust\s+(?:be\s+)?(?:located|reside|live|be based)\s+in\b[^.;\n]*"),
    re.compile(r"(?i)\b(?:authorized|eligible)\s+to\s+work\s+in\b[^.;\n]*"),
    re.compile(r"(?i)\b(?:work|working)\s+(?:hours|timezone|time zone)\s+(?:in|overlapping|aligned)\b[^.;\n]*"),
    re.compile(r"(?i)\b(?:within|must have)\s+\d{1,2}\s+hours?\s+of\s+(?:UTC|GMT)\b[^.;\n]*"),
    re.compile(r"(?i)\b(?:payroll|legal entity|employment entity)\b[^.;\n]{0,50}\b(?:only|limited|available)\b"),
)
_REMOTE_WORLDWIDE = (
    re.compile(r"(?i)\bremote\s*[,;/—-]?\s*(?:worldwide|globally)\b"),
    re.compile(r"(?i)\bworldwide\s+remote\b"),
    re.compile(r"(?i)\b(?:work|working)\s+from\s+anywhere(?:\s+in\s+the\s+world)?\b"),
    re.compile(r"(?i)\banywhere\s+in\s+the\s+world\b"),
    re.compile(r"(?i)\bopen\s+to\s+(?:candidates|applicants)\s+(?:worldwide|globally)\b"),
)
_VISA_NONE = (
    re.compile(r"(?i)\bno\s+(?:visa\s+)?sponsorship\b"),
    re.compile(r"(?i)\bsponsorship\s+(?:is\s+)?not\s+(?:available|offered|provided)\b"),
    re.compile(r"(?i)\bnot\s+(?:eligible|able)\s+(?:for|to\s+(?:offer|provide))\s+(?:visa\s+)?sponsorship\b"),
    re.compile(r"(?i)\b(?:unable|not\s+able|do\s+not|does\s+not|cannot|can't|won't|will\s+not)\s+(?:offer\s+|provide\s+)?sponsor(?:ship)?\b"),
    re.compile(r"(?i)\bmust\s+(?:already\s+)?have\s+(?:the\s+)?right\s+to\s+work\b[^.;\n]*"),
)
_VISA_EXPLICIT = (
    re.compile(r"(?i)\bvisa\s+sponsorship\s+(?:is\s+)?(?:available|offered|provided|supported)\b"),
    re.compile(r"(?i)\b(?:offer|offers|offering|provide|provides|providing)\s+(?:work\s+)?visa\s+sponsorship\b"),
    re.compile(r"(?i)\bwe\s+(?:can\s+|will\s+)?sponsor\s+(?:work\s+)?visas?\b"),
    re.compile(r"(?i)\b(?:employer|company)[- ]sponsored\s+(?:work\s+)?visas?\b"),
    re.compile(r"(?i)\b(?:work|employment)\s+visa\s+(?:support|provided|available)\b"),
)
_RELOCATION_NONE = (
    re.compile(r"(?i)\bno\s+relocation\s+(?:assistance|package|support)\b"),
    re.compile(r"(?i)\brelocation\s+(?:is\s+)?not\s+(?:available|offered|provided|supported)\b"),
)
_RELOCATION_EXPLICIT = (
    re.compile(r"(?i)\brelocation\s+(?:assistance|package|support)\s+(?:is\s+)?(?:available|offered|provided|included)\b"),
    re.compile(r"(?i)\b(?:offer|offers|offering|provide|provides|providing|includes?)\s+(?:a\s+)?relocation\s+(?:assistance|package|support)\b"),
    re.compile(r"(?i)\brelocation\s+(?:is\s+)?(?:available|offered|provided|supported)\b"),
    re.compile(r"(?i)\bwe\s+(?:can\s+|will\s+)?relocate\s+(?:successful\s+)?(?:candidates|applicants|you)\b"),
    re.compile(r"(?i)\b(?:employer|company)[- ](?:sponsored|provided)\s+work\s+permit\b"),
)
_REMOTE_MODE = re.compile(r"(?i)\b(?:remote|work[- ]from[- ]home|wfh|work(?:ing)?\s+from\s+anywhere)\b")


def _first(patterns: Iterable[re.Pattern[str]], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(0).strip()
    return None


def classify_remote(text: str) -> Evidence:
    restricted = _first(_REMOTE_RESTRICTED, text)
    if restricted:
        return Evidence(RemoteScope.RESTRICTED, restricted)
    worldwide = _first(_REMOTE_WORLDWIDE, text)
    if worldwide and _REMOTE_MODE.search(text):
        return Evidence(RemoteScope.WORLDWIDE, worldwide)
    remote = _REMOTE_MODE.search(text)
    return Evidence(
        RemoteScope.UNCLEAR,
        remote.group(0) if remote else "no decisive phrase found",
    )


def _classify_offer(
    text: str,
    negatives: Iterable[re.Pattern[str]],
    positives: Iterable[re.Pattern[str]],
) -> Evidence:
    negative = _first(negatives, text)
    if negative:
        return Evidence(Sponsorship.NONE, negative)
    positive = _first(positives, text)
    if positive:
        return Evidence(Sponsorship.EXPLICIT, positive)
    return Evidence(Sponsorship.UNCLEAR, "no decisive phrase found")


def classify_sponsorship(text: str) -> Evidence:
    return _classify_offer(text, _VISA_NONE, _VISA_EXPLICIT)


def classify_relocation(text: str) -> Evidence:
    return _classify_offer(text, _RELOCATION_NONE, _RELOCATION_EXPLICIT)
