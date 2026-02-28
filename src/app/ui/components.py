from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
from typing import Any
from urllib.parse import urlparse

from sqlmodel import Session

from app.models.repositories import JobRepository
from app.models.tables import Job, JobStatus
from app.services.extraction_dom import FieldCandidate
from app.services.scoring import ScoreResult, load_profile, score_job

MAPPINGS_PATH = Path("data/mappings/site_mappings.json")


def get_default_profile_path() -> Path | None:
    candidates = [
        Path("profile.yaml"),
        Path("data/profile.yaml"),
        Path("tests/fixtures/profile_mapping.yaml"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def compute_job_score(job: Job, profile_path: Path | None) -> ScoreResult | None:
    if profile_path is None or not profile_path.exists():
        return None
    profile = load_profile(profile_path)
    return score_job(job.description or "", profile)


def list_jobs_with_score(session: Session, profile_path: Path | None) -> list[dict[str, Any]]:
    repository = JobRepository(session)
    rows: list[dict[str, Any]] = []
    for job in repository.list():
        score_result = compute_job_score(job, profile_path)
        rows.append(
            {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location or "",
                "status": job.status.value,
                "url": job.source_url or "",
                "source": job.source or "",
                "score": score_result.score if score_result else None,
                "score_reasons": score_result.reasons if score_result else [],
                "job": job,
            }
        )
    rows.sort(
        key=lambda item: (
            item["score"] is None,
            -(item["score"] or -1),
            item["title"].lower(),
        )
    )
    return rows


def mark_job_applied(session: Session, job_id: int) -> Job | None:
    repository = JobRepository(session)
    return repository.update(job_id, status=JobStatus.APPLIED)


def get_domain_key(url: str | None) -> str:
    if not url:
        return "manual"
    parsed = urlparse(url)
    return parsed.netloc.lower() or "manual"


def load_site_mappings() -> dict[str, dict[str, dict[str, Any]]]:
    if not MAPPINGS_PATH.exists():
        return {}
    return json.loads(MAPPINGS_PATH.read_text(encoding="utf-8"))


def save_site_mapping(
    site_key: str,
    field_candidates: list[FieldCandidate],
) -> None:
    payload = load_site_mappings()
    payload[site_key] = {
        candidate.selector: {
            "canonical_key": candidate.canonical_key,
            "proposed_value": candidate.proposed_value,
            "confidence": candidate.confidence,
            "raw_label": candidate.raw_label,
            "raw_name_or_id": candidate.raw_name_or_id,
            "inferred_type": candidate.inferred_type,
            "reasons": candidate.reasons,
        }
        for candidate in field_candidates
    }
    MAPPINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAPPINGS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def apply_saved_mapping(
    site_key: str,
    field_candidates: list[FieldCandidate],
) -> list[FieldCandidate]:
    saved = load_site_mappings().get(site_key, {})
    merged: list[FieldCandidate] = []
    for candidate in field_candidates:
        override = saved.get(candidate.selector)
        if not override:
            merged.append(candidate)
            continue
        merged.append(
            FieldCandidate(
                selector=candidate.selector,
                raw_label=candidate.raw_label,
                raw_name_or_id=candidate.raw_name_or_id,
                inferred_type=candidate.inferred_type,
                canonical_key=override.get("canonical_key") or candidate.canonical_key,
                proposed_value=override.get("proposed_value") or candidate.proposed_value,
                confidence=float(override.get("confidence", candidate.confidence)),
                reasons=list(override.get("reasons") or candidate.reasons),
            )
        )
    return merged


def field_candidates_to_rows(
    field_candidates: list[FieldCandidate],
) -> list[dict[str, Any]]:
    return [asdict(candidate) for candidate in field_candidates]
