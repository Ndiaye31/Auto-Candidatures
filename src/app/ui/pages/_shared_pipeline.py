from __future__ import annotations

import streamlit as st

from app.models.db import get_session
from app.services.ats import ApplicationStage, get_pipeline_cards
from app.ui.components import get_active_profile_id
from app.utils.logging import get_logger

LOGGER = get_logger("ui.pipeline")


def render() -> None:
    st.title("Pipeline ATS")
    try:
        with get_session() as session:
            profile_id = get_active_profile_id(session)
            cards = get_pipeline_cards(session, profile_id=profile_id)
    except Exception as exc:
        LOGGER.exception("Failed to load ATS pipeline")
        st.error("Impossible de charger le pipeline ATS.")
        st.exception(exc)
        return

    if not cards:
        st.info("Aucune candidature ATS pour le profil actif.")
        return

    stages = [
        ApplicationStage.SOURCED,
        ApplicationStage.TO_REVIEW,
        ApplicationStage.PACK_READY,
        ApplicationStage.APPLIED,
        ApplicationStage.SCREENING,
        ApplicationStage.INTERVIEW_HR,
        ApplicationStage.INTERVIEW_TECH,
        ApplicationStage.CASE_STUDY,
        ApplicationStage.FINAL_INTERVIEW,
        ApplicationStage.OFFER,
        ApplicationStage.REJECTED,
    ]
    columns = st.columns(3)
    for index, stage in enumerate(stages):
        with columns[index % 3]:
            stage_cards = [card for card in cards if card.stage == stage]
            st.subheader(stage.value)
            st.caption(f"{len(stage_cards)} candidature(s)")
            for card in stage_cards:
                with st.container(border=True):
                    st.write(f"**{card.job_title}**")
                    st.caption(card.company)
                    if card.next_step:
                        st.write(f"Prochaine action: {card.next_step}")
                    if card.next_step_due_at:
                        st.caption(
                            f"Echeance: {card.next_step_due_at.date().isoformat()}"
                        )
                    if st.button(
                        "Ouvrir",
                        key=f"pipeline-open-{card.application.id}",
                        use_container_width=True,
                    ):
                        st.session_state["selected_job_id"] = card.application.job_id
                        st.session_state["current_page"] = "detail"
                        st.rerun()
