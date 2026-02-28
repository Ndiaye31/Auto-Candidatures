from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import yaml

WORD_BOUNDARY_TEMPLATE = r"(?<!\w){term}(?!\w)"
SENIORITY_ORDER = {
    "intern": 0,
    "junior": 1,
    "mid": 2,
    "senior": 3,
    "lead": 4,
    "staff": 5,
    "principal": 6,
}
REMOTE_ALIASES = {
    "remote": "remote",
    "full remote": "remote",
    "hybrid": "hybrid",
    "on-site": "onsite",
    "on site": "onsite",
    "onsite": "onsite",
}


@dataclass(slots=True)
class ScoreReason:
    category: str
    label: str
    impact: float
    evidence: str


@dataclass(slots=True)
class ScoreResult:
    score: int
    reasons: list[ScoreReason]


@dataclass(slots=True)
class RankedJob:
    title: str
    score: int
    reasons: list[ScoreReason]


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def _contains_term(text: str, term: str) -> bool:
    pattern = WORD_BOUNDARY_TEMPLATE.format(term=re.escape(_normalize_text(term)))
    return re.search(pattern, text) is not None


def load_profile(profile_path: str | Path) -> dict[str, Any]:
    with Path(profile_path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return payload


def _score_keywords(description: str, profile: dict[str, Any]) -> list[ScoreReason]:
    reasons: list[ScoreReason] = []
    for item in profile.get("keywords", []):
        term = str(item.get("term", "")).strip()
        weight = float(item.get("weight", 0))
        if term and _contains_term(description, term):
            reasons.append(
                ScoreReason(
                    category="keyword",
                    label=f"Keyword match: {term}",
                    impact=weight,
                    evidence=f"'{term}' found in the job description.",
                )
            )
    return reasons


def _score_stack(description: str, profile: dict[str, Any]) -> list[ScoreReason]:
    reasons: list[ScoreReason] = []
    target_stack = [str(item).strip() for item in profile.get("target_stack", []) if item]
    for technology in target_stack:
        if _contains_term(description, technology):
            reasons.append(
                ScoreReason(
                    category="stack",
                    label=f"Target stack: {technology}",
                    impact=6.0,
                    evidence=f"'{technology}' matches the target stack.",
                )
            )
    return reasons


def _extract_remote_mode(text: str) -> str | None:
    for alias, normalized in REMOTE_ALIASES.items():
        if alias in text:
            return normalized
    return None


def _score_remote(description: str, profile: dict[str, Any]) -> list[ScoreReason]:
    preference = _normalize_text(profile.get("preferences", {}).get("remote"))
    if not preference:
        return []

    remote_mode = _extract_remote_mode(description)
    if remote_mode is None:
        return []

    if preference == "preferred":
        if remote_mode == "remote":
            return [
                ScoreReason(
                    category="bonus",
                    label="Remote preferred",
                    impact=8.0,
                    evidence="The offer is remote and the profile prefers remote work.",
                )
            ]
        if remote_mode == "hybrid":
            return [
                ScoreReason(
                    category="bonus",
                    label="Hybrid acceptable",
                    impact=3.0,
                    evidence="The offer is hybrid, which partially matches the remote preference.",
                )
            ]
        return [
            ScoreReason(
                category="malus",
                label="Onsite role",
                impact=-6.0,
                evidence="The offer is onsite while the profile prefers remote work.",
            )
        ]

    if preference == "required":
        if remote_mode == "remote":
            return [
                ScoreReason(
                    category="bonus",
                    label="Remote required",
                    impact=10.0,
                    evidence="The offer satisfies the remote requirement.",
                )
            ]
        return [
            ScoreReason(
                category="malus",
                label="Remote requirement not met",
                impact=-15.0,
                evidence="The offer is not fully remote.",
            )
        ]

    return []


def _extract_seniority(text: str) -> str | None:
    for level in SENIORITY_ORDER:
        if _contains_term(text, level):
            return level
    return None


def _score_seniority(description: str, profile: dict[str, Any]) -> list[ScoreReason]:
    target_level = _normalize_text(profile.get("preferences", {}).get("seniority"))
    if target_level not in SENIORITY_ORDER:
        return []

    job_level = _extract_seniority(description)
    if job_level is None:
        return []

    diff = SENIORITY_ORDER[job_level] - SENIORITY_ORDER[target_level]
    if diff == 0:
        return [
            ScoreReason(
                category="bonus",
                label="Matching seniority",
                impact=7.0,
                evidence=f"The offer targets a {job_level} profile, matching the target seniority.",
            )
        ]
    if diff > 0:
        return [
            ScoreReason(
                category="malus",
                label="Seniority too high",
                impact=-5.0 - (2.0 * max(diff - 1, 0)),
                evidence=f"The offer targets {job_level}, above the target seniority.",
            )
        ]
    return [
        ScoreReason(
            category="malus",
            label="Seniority below target",
            impact=-3.0,
            evidence=f"The offer targets {job_level}, below the target seniority.",
        )
    ]


def score_job(description: str, profile: dict[str, Any]) -> ScoreResult:
    normalized_description = _normalize_text(description)
    reasons = [
        *_score_keywords(normalized_description, profile),
        *_score_stack(normalized_description, profile),
        *_score_remote(normalized_description, profile),
        *_score_seniority(normalized_description, profile),
    ]
    raw_score = 50.0 + sum(reason.impact for reason in reasons)
    bounded_score = max(0, min(100, int(round(raw_score))))
    reasons.sort(key=lambda reason: abs(reason.impact), reverse=True)
    return ScoreResult(score=bounded_score, reasons=reasons)


def rank_jobs(jobs: list[dict[str, str]], profile_path: str | Path) -> list[RankedJob]:
    profile = load_profile(profile_path)
    ranked: list[RankedJob] = []
    for job in jobs:
        result = score_job(job.get("description", ""), profile)
        ranked.append(
            RankedJob(
                title=job.get("title", ""),
                score=result.score,
                reasons=result.reasons,
            )
        )
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked
