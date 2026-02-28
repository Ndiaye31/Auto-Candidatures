from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
from typing import Any
from urllib.parse import urlparse

import streamlit as st
from sqlmodel import Session

from app.models.repositories import ApplicationRepository, CandidateProfileRepository, JobRepository
from app.models.tables import CandidateProfile, Job, JobStatus
from app.services.extraction_dom import FieldCandidate
from app.services.scoring import ScoreResult, load_profile, score_job
from app.services.profile_loader import load_profile_payload
from app.services.profiles import ensure_default_profile
from app.utils.logging import get_logger

MAPPINGS_PATH = Path("data/mappings/site_mappings.json")
LOGGER = get_logger("ui.components")


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


def get_active_profile(session: Session) -> CandidateProfile | None:
    repository = CandidateProfileRepository(session)
    selected_profile_id = st.session_state.get("active_profile_id")
    if selected_profile_id is not None:
        profile = repository.get(int(selected_profile_id))
        if profile is not None:
            return profile
    profile = repository.get_default()
    if profile is None:
        profile = ensure_default_profile(session)
    if profile is not None:
        st.session_state["active_profile_id"] = profile.id
    return profile


def get_active_profile_payload(session: Session) -> tuple[CandidateProfile | None, dict[str, Any] | None]:
    profile = get_active_profile(session)
    if profile is not None:
        return profile, load_profile_payload(profile_yaml=profile.profile_yaml)

    profile_path = get_default_profile_path()
    if profile_path is None:
        return None, None
    return None, load_profile_payload(profile_path=profile_path)


def get_active_profile_id(session: Session) -> int | None:
    profile = get_active_profile(session)
    return profile.id if profile is not None else None


def compute_job_score(
    job: Job,
    profile_path: Path | None = None,
    *,
    profile_yaml: str | None = None,
    profile_data: dict[str, Any] | None = None,
) -> ScoreResult | None:
    if profile_path is None and profile_yaml is None and profile_data is None:
        return None
    try:
        profile = load_profile(
            profile_path,
            profile_yaml=profile_yaml,
            profile_data=profile_data,
        )
        return score_job(job.description or "", profile)
    except Exception:
        LOGGER.exception("Failed to compute score", extra={"job_id": job.id})
        return None


def list_jobs_with_score(
    session: Session,
    profile_path: Path | None = None,
    *,
    profile_yaml: str | None = None,
    profile_data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    repository = JobRepository(session)
    rows: list[dict[str, Any]] = []
    active_profile_id = get_active_profile_id(session)
    for job in repository.list():
        score_result = compute_job_score(
            job,
            profile_path,
            profile_yaml=profile_yaml,
            profile_data=profile_data,
        )
        application = None
        if active_profile_id is not None:
            application = ApplicationRepository(session).get_by_job_and_profile(
                job.id, active_profile_id
            )
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
                "application_id": application.id if application else None,
                "application_stage": application.stage.value if application else "",
                "next_step": application.next_step if application else "",
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
    try:
        return json.loads(MAPPINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        LOGGER.exception("Invalid mapping file", extra={"path": str(MAPPINGS_PATH)})
        return {}


def save_site_mapping(
    site_key: str,
    field_candidates: list[FieldCandidate],
) -> None:
    if not site_key.strip():
        raise ValueError("Le domaine/site ne peut pas etre vide.")
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
