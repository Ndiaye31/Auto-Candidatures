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
WORKFLOW_SEQUENCE = ("offres", "detail", "postuler")
WORKFLOW_LABELS = {
    "offres": "1. Selection offre",
    "detail": "2. Generation pack",
    "postuler": "3. Postuler assiste",
}


def render_app_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top right, rgba(12, 74, 110, 0.08), transparent 28rem),
                linear-gradient(180deg, #f8fafc 0%, #eef4f7 100%);
        }
        html, body, [class*="css"] {
            font-family: "Aptos", "Segoe UI", sans-serif;
        }
        .workflow-shell {
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid rgba(15, 23, 42, 0.08);
            border-radius: 18px;
            padding: 1rem 1.1rem;
            box-shadow: 0 16px 40px rgba(15, 23, 42, 0.06);
            backdrop-filter: blur(10px);
            margin-bottom: 1rem;
        }
        .workflow-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.8rem;
            margin-top: 0.8rem;
        }
        .workflow-step {
            border-radius: 16px;
            padding: 0.95rem 1rem;
            background: #f8fafc;
            border: 1px solid rgba(148, 163, 184, 0.28);
        }
        .workflow-step.active {
            background: linear-gradient(135deg, #0f766e, #155e75);
            color: white;
            border-color: transparent;
        }
        .workflow-step.complete {
            background: linear-gradient(135deg, rgba(21, 128, 61, 0.12), rgba(15, 118, 110, 0.12));
            border-color: rgba(21, 128, 61, 0.22);
        }
        .workflow-index {
            font-size: 0.8rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            opacity: 0.7;
        }
        .workflow-title {
            font-size: 1.02rem;
            font-weight: 700;
            margin-top: 0.3rem;
        }
        .workflow-copy {
            font-size: 0.92rem;
            margin-top: 0.25rem;
            opacity: 0.84;
        }
        .summary-card {
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid rgba(15, 23, 42, 0.08);
            border-radius: 18px;
            padding: 1rem 1.1rem;
            box-shadow: 0 12px 24px rgba(15, 23, 42, 0.05);
        }
        .summary-kicker {
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.74rem;
            color: #0f766e;
            font-weight: 700;
        }
        .summary-title {
            font-size: 1.18rem;
            font-weight: 700;
            color: #0f172a;
            margin-top: 0.25rem;
        }
        .summary-meta {
            color: #475569;
            font-size: 0.95rem;
            margin-top: 0.25rem;
        }
        .section-hint {
            color: #475569;
            font-size: 0.95rem;
            margin-bottom: 0.75rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def push_flash(level: str, message: str) -> None:
    st.session_state["workflow_flash"] = {"level": level, "message": message}


def render_flash() -> None:
    flash = st.session_state.pop("workflow_flash", None)
    if not flash:
        return
    level = flash.get("level", "info")
    message = str(flash.get("message", ""))
    display = getattr(st, level, st.info)
    display(message)


def set_current_page(page: str) -> None:
    st.session_state["current_page"] = page


def go_to_page(page: str, *, selected_job_id: int | None = None) -> None:
    if selected_job_id is not None:
        st.session_state["selected_job_id"] = selected_job_id
    if page in WORKFLOW_SEQUENCE:
        st.session_state["workflow_step"] = page
    set_current_page(page)
    st.rerun()


def get_selected_job_id() -> int | None:
    selected_job_id = st.session_state.get("selected_job_id")
    if selected_job_id is None:
        return None
    return int(selected_job_id)


def is_pack_ready_for_job(job_id: int | None) -> bool:
    if job_id is None:
        return False
    if st.session_state.get("last_pack_job_id") != job_id:
        return False
    output_dir = st.session_state.get("last_pack_dir")
    return bool(output_dir and Path(output_dir).exists())


def render_workflow_header(current_page: str, *, selected_job: Job | None = None) -> None:
    selected_job_id = selected_job.id if selected_job is not None else get_selected_job_id()
    pack_ready = is_pack_ready_for_job(selected_job_id)
    current_primary = current_page if current_page in WORKFLOW_SEQUENCE else "offres"
    current_index = WORKFLOW_SEQUENCE.index(current_primary)
    completed = {
        "offres": selected_job_id is not None,
        "detail": pack_ready,
        "postuler": False,
    }
    copy_map = {
        "offres": "Choisir une offre, filtrer et verifier son score.",
        "detail": "Generer les documents et preparer le dossier.",
        "postuler": "Piloter le remplissage sans jamais soumettre.",
    }
    cards: list[str] = []
    for index, page in enumerate(WORKFLOW_SEQUENCE, start=1):
        classes = ["workflow-step"]
        if page == current_primary:
            classes.append("active")
        elif completed.get(page):
            classes.append("complete")
        cards.append(
            "<div class='{classes}'>"
            "<div class='workflow-index'>Etape {index}</div>"
            "<div class='workflow-title'>{title}</div>"
            "<div class='workflow-copy'>{copy}</div>"
            "</div>".format(
                classes=" ".join(classes),
                index=index,
                title=WORKFLOW_LABELS[page],
                copy=copy_map[page],
            )
        )

    selected_copy = "Aucune offre selectionnee."
    if selected_job is not None:
        selected_copy = f"Offre active: {selected_job.title} · {selected_job.company}"

    st.markdown(
        (
            "<div class='workflow-shell'>"
            "<div class='summary-kicker'>Workflow candidature</div>"
            "<div class='summary-title'>Parcours guide en 3 etapes</div>"
            f"<div class='summary-meta'>{selected_copy}</div>"
            f"<div class='workflow-grid'>{''.join(cards)}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_job_summary_card(
    *,
    title: str,
    company: str,
    meta: str,
    kicker: str = "Offre selectionnee",
) -> None:
    st.markdown(
        (
            "<div class='summary-card'>"
            f"<div class='summary-kicker'>{kicker}</div>"
            f"<div class='summary-title'>{title} · {company}</div>"
            f"<div class='summary-meta'>{meta}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


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
