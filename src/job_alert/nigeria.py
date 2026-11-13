from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NigeriaDecision:
    keep: bool
    note: str = ""
    phrase: str = ""


# Includes all states/FCT and major cities whose names commonly appear instead of a state.
_PLACE_TO_STATE = {
    "abia": "Abia",
    "umuahia": "Abia",
    "aba": "Abia",
    "adamawa": "Adamawa",
    "yola": "Adamawa",
    "akwa ibom": "Akwa Ibom",
    "uyo": "Akwa Ibom",
    "eket": "Akwa Ibom",
    "anambra": "Anambra",
    "awka": "Anambra",
    "onitsha": "Anambra",
    "nnewi": "Anambra",
    "bauchi": "Bauchi",
    "bayelsa": "Bayelsa",
    "yenagoa": "Bayelsa",
    "benue": "Benue",
    "makurdi": "Benue",
    "borno": "Borno",
    "maiduguri": "Borno",
    "cross river": "Cross River",
    "calabar": "Cross River",
    "delta": "Delta",
    "asaba": "Delta",
    "warri": "Delta",
    "ebonyi": "Ebonyi",
    "abakaliki": "Ebonyi",
    "edo": "Edo",
    "benin city": "Edo",
    "ekiti": "Ekiti",
    "ado-ekiti": "Ekiti",
    "enugu": "Enugu",
    "fct": "FCT",
    "abuja": "FCT",
    "federal capital territory": "FCT",
    "gombe": "Gombe",
    "imo": "Imo",
    "owerri": "Imo",
    "jigawa": "Jigawa",
    "dutse": "Jigawa",
    "kaduna": "Kaduna",
    "zaria": "Kaduna",
    "kano": "Kano",
    "katsina": "Katsina",
    "kebbi": "Kebbi",
    "birnin kebbi": "Kebbi",
    "kogi": "Kogi",
    "lokoja": "Kogi",
    "kwara": "Kwara",
    "ilorin": "Kwara",
    "lagos": "Lagos",
    "nasarawa": "Nasarawa",
    "lafia": "Nasarawa",
    "neighbouring nasarawa": "Nasarawa",
    "niger state": "Niger",
    "minna": "Niger",
    "ogun": "Ogun",
    "abeokuta": "Ogun",
    "sagamu": "Ogun",
    "ota": "Ogun",
    "ondo": "Ondo",
    "akure": "Ondo",
    "osun": "Osun",
    "osogbo": "Osun",
    "ile-ife": "Osun",
    "oyo": "Oyo",
    "ibadan": "Oyo",
    "plateau": "Plateau",
    "jos": "Plateau",
    "rivers": "Rivers",
    "port harcourt": "Rivers",
    "sokoto": "Sokoto",
    "taraba": "Taraba",
    "jalingo": "Taraba",
    "yobe": "Yobe",
    "damaturu": "Yobe",
    "zamfara": "Zamfara",
    "gusau": "Zamfara",
}

_REMOTE_RE = re.compile(r"(?i)\b(remote|work[- ]from[- ]home|wfh|hybrid|flexible)\b")
_ONSITE_RE = re.compile(r"(?i)\bon[- ]?site\b")
_AMBIGUOUS_LAGOS_ALIASES = {"maryland", "vi"}
_RESTRICTIVE_RE = re.compile(
    r"(?i)\b(?:on[- ]?site(?:\s+(?:in|at))?|must\s+(?:be\s+)?(?:based|located|reside|live)\s+in|"
    r"relocat(?:e|ion)\s+to|required\s+to\s+work\s+(?:in|from))\b"
)


def _contains(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, re.IGNORECASE))


def classify_nigeria(
    location: str,
    description: str,
    work_mode: str,
    lagos_aliases: tuple[str, ...] | list[str],
) -> NigeriaDecision:
    text = " ".join((location, work_mode, description))
    location_context = " ".join((location, work_mode))
    for alias in sorted(lagos_aliases, key=len, reverse=True):
        if not _contains(location_context, alias):
            continue
        if alias.casefold() in _AMBIGUOUS_LAGOS_ALIASES and not re.search(
            r"(?i)\b(?:lagos|nigeria)\b", text
        ):
            continue
        return NigeriaDecision(True, phrase=alias)

    mentions: list[tuple[str, str]] = []
    for place, state in sorted(_PLACE_TO_STATE.items(), key=lambda item: len(item[0]), reverse=True):
        if state == "Lagos":
            continue
        if _contains(location_context, place):
            mentions.append((place, state))
    # Preserve only the first distinct state in the source wording.
    other = mentions[0] if mentions else None

    if other:
        place, state = other
        onsite = _ONSITE_RE.search(work_mode) or _ONSITE_RE.search(description)
        if onsite and not _REMOTE_RE.search(text):
            return NigeriaDecision(False, phrase=onsite.group(0))
        for match in _RESTRICTIVE_RE.finditer(text):
            window = text[max(0, match.start() - 80) : match.end() + 80]
            if _contains(window, place) or _contains(window, state):
                return NigeriaDecision(False, phrase=window.strip())
        return NigeriaDecision(
            True,
            note=f"{state}: check if working from Lagos is OK",
            phrase=place,
        )

    if re.search(r"(?i)\bnigeria(?:n)?\b", text):
        restrictive = _RESTRICTIVE_RE.search(text)
        if restrictive and not _REMOTE_RE.search(text):
            return NigeriaDecision(False, phrase=restrictive.group(0))
        remote = _REMOTE_RE.search(text)
        return NigeriaDecision(True, phrase=remote.group(0) if remote else "Nigeria")

    return NigeriaDecision(False)
