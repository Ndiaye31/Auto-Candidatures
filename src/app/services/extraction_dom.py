from __future__ import annotations

from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any

from app.services.profile_loader import load_profile_payload


@dataclass(slots=True)
class FieldCandidate:
    selector: str
    raw_label: str
    raw_name_or_id: str
    inferred_type: str
    canonical_key: str | None
    proposed_value: str | None
    confidence: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class _FieldNode:
    tag: str
    attrs: dict[str, str]
    raw_label: str = ""
    order: int = 0


class _FormHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: list[_FieldNode] = []
        self._labels_by_for: dict[str, str] = {}
        self._label_stack: list[dict[str, Any]] = []
        self._field_order = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: (value or "") for key, value in attrs}
        if tag == "label":
            self._label_stack.append(
                {
                    "for": attr_map.get("for", "").strip(),
                    "chunks": [],
                    "field_indexes": [],
                }
            )
            return

        if tag not in {"input", "textarea", "select"}:
            return

        node = _FieldNode(tag=tag, attrs=attr_map, order=self._field_order)
        self._field_order += 1
        self.fields.append(node)
        if self._label_stack:
            self._label_stack[-1]["field_indexes"].append(len(self.fields) - 1)

    def handle_endtag(self, tag: str) -> None:
        if tag != "label" or not self._label_stack:
            return

        label_info = self._label_stack.pop()
        label_text = _normalize_text(" ".join(label_info["chunks"]))
        label_for = label_info["for"]
        if label_for and label_text:
            self._labels_by_for[label_for] = label_text
        for index in label_info["field_indexes"]:
            if label_text and not self.fields[index].raw_label:
                self.fields[index].raw_label = label_text

    def handle_data(self, data: str) -> None:
        if self._label_stack:
            self._label_stack[-1]["chunks"].append(data)


def _normalize_text(value: str | None) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip()
    return text


def _normalize_token(value: str | None) -> str:
    lowered = _normalize_text(value).lower()
    return lowered.replace("_", " ").replace("-", " ")


def _profile_value(profile: dict[str, Any], canonical_key: str) -> str | None:
    identity = profile.get("identity", {}) if isinstance(profile.get("identity"), dict) else {}
    preferences = (
        profile.get("preferences", {}) if isinstance(profile.get("preferences"), dict) else {}
    )
    availability = (
        profile.get("availability", {}) if isinstance(profile.get("availability"), dict) else {}
    )
    salary = profile.get("salary", {}) if isinstance(profile.get("salary"), dict) else {}
    urls = profile.get("urls", {}) if isinstance(profile.get("urls"), dict) else {}

    mapping: dict[str, Any] = {
        "candidate.email": identity.get("email"),
        "candidate.phone": identity.get("phone"),
        "candidate.city": identity.get("city") or identity.get("location"),
        "candidate.linkedin_url": urls.get("linkedin"),
        "candidate.github_url": urls.get("github"),
        "candidate.salary_expectation": salary.get("expected") or preferences.get("salary"),
        "candidate.availability": availability.get("start_date")
        or availability.get("notice_period")
        or preferences.get("availability"),
        "candidate.full_name": identity.get("full_name"),
    }
    value = mapping.get(canonical_key)
    return _normalize_text(str(value)) if value is not None else None


def _infer_type(field: _FieldNode) -> str:
    field_type = _normalize_token(field.attrs.get("type"))
    if field.tag == "textarea":
        return "textarea"
    if field.tag == "select":
        return "select"
    return field_type or "text"


def _selector_for(field: _FieldNode) -> str:
    field_id = _normalize_text(field.attrs.get("id"))
    if field_id:
        return f"#{field_id}"
    field_name = _normalize_text(field.attrs.get("name"))
    if field_name:
        return f'{field.tag}[name="{field_name}"]'
    return f"{field.tag}:nth-of-type({field.order + 1})"


def _signal_texts(field: _FieldNode, labels_by_for: dict[str, str]) -> list[tuple[str, str]]:
    signals: list[tuple[str, str]] = []
    field_id = _normalize_text(field.attrs.get("id"))
    if field.raw_label:
        signals.append(("label", field.raw_label))
    elif field_id and field_id in labels_by_for:
        signals.append(("label", labels_by_for[field_id]))

    for source, attr_name in (
        ("name", "name"),
        ("id", "id"),
        ("autocomplete", "autocomplete"),
        ("aria-label", "aria-label"),
        ("placeholder", "placeholder"),
    ):
        value = _normalize_text(field.attrs.get(attr_name))
        if value:
            signals.append((source, value))
    return signals


CANONICAL_RULES: dict[str, dict[str, Any]] = {
    "candidate.email": {
        "keywords": {"email", "e-mail", "mail", "courriel"},
        "autocomplete": {"email"},
        "types": {"email"},
    },
    "candidate.phone": {
        "keywords": {"phone", "telephone", "téléphone", "mobile", "tel", "gsm"},
        "autocomplete": {"tel"},
        "types": {"tel"},
    },
    "candidate.city": {
        "keywords": {"city", "ville", "location", "localisation", "commune"},
        "autocomplete": {"address-level2", "address-level1", "home city"},
        "types": {"text", "search"},
    },
    "candidate.linkedin_url": {
        "keywords": {"linkedin", "linked in", "profil linkedin"},
        "autocomplete": {"url"},
        "types": {"url", "text"},
    },
    "candidate.github_url": {
        "keywords": {"github", "git hub", "portfolio github"},
        "autocomplete": {"url"},
        "types": {"url", "text"},
    },
    "candidate.salary_expectation": {
        "keywords": {
            "salary",
            "salaire",
            "pretention salariale",
            "prétention salariale",
            "compensation",
            "remuneration",
            "rémunération",
        },
        "autocomplete": {"off"},
        "types": {"number", "text"},
    },
    "candidate.availability": {
        "keywords": {
            "availability",
            "disponibilite",
            "disponibilité",
            "start date",
            "notice period",
            "dispo",
        },
        "autocomplete": {"off"},
        "types": {"date", "text"},
    },
    "candidate.full_name": {
        "keywords": {"full name", "nom complet", "name", "nom et prenom", "nom prénom"},
        "autocomplete": {"name"},
        "types": {"text"},
    },
}

SOURCE_WEIGHTS = {
    "label": 0.38,
    "name": 0.2,
    "id": 0.15,
    "autocomplete": 0.18,
    "aria-label": 0.16,
    "placeholder": 0.12,
}
TYPE_BONUS = 0.1


def _match_rule(
    canonical_key: str,
    field: _FieldNode,
    signal_texts: list[tuple[str, str]],
) -> tuple[float, list[str]]:
    rule = CANONICAL_RULES[canonical_key]
    matched_reasons: list[str] = []
    score = 0.0

    for source, raw_value in signal_texts:
        tokenized = _normalize_token(raw_value)
        keywords = rule["keywords"]
        autocomplete_values = rule["autocomplete"]
        if source == "autocomplete" and tokenized in autocomplete_values:
            score += SOURCE_WEIGHTS[source]
            matched_reasons.append(
                f"autocomplete='{raw_value}' matches {canonical_key}"
            )
            continue

        if any(keyword in tokenized for keyword in keywords):
            score += SOURCE_WEIGHTS[source]
            matched_reasons.append(f"{source}='{raw_value}' suggests {canonical_key}")

    inferred_type = _infer_type(field)
    if inferred_type in rule["types"]:
        score += TYPE_BONUS
        matched_reasons.append(
            f"field type '{inferred_type}' is compatible with {canonical_key}"
        )

    return score, matched_reasons


def map_form_fields(
    html: str,
    profile_path: str | Path | None = None,
    *,
    profile_yaml: str | None = None,
    profile_data: dict[str, Any] | None = None,
) -> list[FieldCandidate]:
    parser = _FormHTMLParser()
    parser.feed(html)
    profile = load_profile_payload(
        profile_path=profile_path,
        profile_yaml=profile_yaml,
        profile_data=profile_data,
    )

    candidates: list[FieldCandidate] = []
    for field in parser.fields:
        signals = _signal_texts(field, parser._labels_by_for)
        best_key: str | None = None
        best_score = 0.0
        best_reasons: list[str] = []

        for canonical_key in CANONICAL_RULES:
            score, reasons = _match_rule(canonical_key, field, signals)
            if score > best_score:
                best_score = score
                best_key = canonical_key
                best_reasons = reasons

        confidence = max(0.0, min(1.0, round(best_score, 2)))
        proposed_value = _profile_value(profile, best_key) if best_key else None
        raw_name_or_id = _normalize_text(field.attrs.get("name")) or _normalize_text(
            field.attrs.get("id")
        )
        candidates.append(
            FieldCandidate(
                selector=_selector_for(field),
                raw_label=field.raw_label or parser._labels_by_for.get(field.attrs.get("id", ""), ""),
                raw_name_or_id=raw_name_or_id,
                inferred_type=_infer_type(field),
                canonical_key=best_key if confidence >= 0.25 else None,
                proposed_value=proposed_value if confidence >= 0.25 else None,
                confidence=confidence,
                reasons=best_reasons if confidence >= 0.25 else ["No strong mapping signal found"],
            )
        )

    return candidates
