from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.models.db import get_session
from app.models.repositories import JobRepository
from app.services.generation_pack import generate_application_pack
from app.ui.components import compute_job_score, get_default_profile_path, mark_job_applied


def render() -> None:
    st.title("Detail offre")
    job_id = st.session_state.get("selected_job_id")
    if not job_id:
        st.info("Selectionne une offre depuis la page Offres.")
        return

    with get_session() as session:
        job = JobRepository(session).get(int(job_id))
    if job is None:
        st.error("Offre introuvable.")
        return

    profile_path = get_default_profile_path()
    score_result = compute_job_score(job, profile_path)

    title_col, action_col1, action_col2, action_col3 = st.columns([4, 1, 1, 1])
    title_col.subheader(f"{job.title} · {job.company}")
    if job.source_url:
        action_col1.link_button("Ouvrir URL", job.source_url, use_container_width=True)
    if action_col2.button("Generer pack", use_container_width=True):
        if profile_path is None:
            st.error("Aucun profile.yaml disponible.")
        else:
            result = generate_application_pack(job, Path(profile_path), Path("data/packs"))
            st.session_state["last_pack_dir"] = str(result.output_dir)
            st.success(f"Pack genere dans {result.output_dir}")
    if action_col3.button("Postuler assiste", use_container_width=True):
        st.session_state["current_page"] = "postuler"
        st.rerun()

    if st.button("Marquer applied"):
        with get_session() as session:
            mark_job_applied(session, int(job.id))
        st.success("Offre marquee comme applied.")

    info_col1, info_col2, info_col3 = st.columns(3)
    info_col1.metric("Statut", job.status.value)
    info_col2.metric("Localisation", job.location or "N/A")
    info_col3.metric("Score", score_result.score if score_result else "N/A")

    st.write(job.description or "Description non renseignee.")
    if score_result:
        st.caption("Explication du score")
        for reason in score_result.reasons:
            st.write(f"- {reason.label} ({reason.impact:+.1f})")
            st.caption(reason.evidence)

    if st.session_state.get("last_pack_dir"):
        st.info(f"Dernier pack genere: {st.session_state['last_pack_dir']}")
