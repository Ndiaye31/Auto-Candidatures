from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path

import streamlit as st

from app.models.db import get_session
from app.models.repositories import ApplicationRepository, JobRepository
from app.models.tables import ApplicationStage
from app.services.ats import (
    AtsError,
    add_application_event,
    add_contact,
    ensure_application,
    get_application_contacts,
    get_application_timeline,
    update_application_stage,
)
from app.services.generation_pack import generate_application_pack
from app.ui.components import (
    compute_job_score,
    get_active_profile_payload,
    mark_job_applied,
)
from app.utils.logging import get_logger

LOGGER = get_logger("ui.detail")


def render() -> None:
    st.title("Detail offre")
    job_id = st.session_state.get("selected_job_id")
    if not job_id:
        st.info("Selectionne une offre depuis la page Offres.")
        return

    try:
        with get_session() as session:
            job = JobRepository(session).get(int(job_id))
    except Exception as exc:
        LOGGER.exception("Failed to load job detail", extra={"job_id": job_id})
        st.error("Impossible de charger cette offre.")
        st.exception(exc)
        return
    if job is None:
        st.error("Offre introuvable.")
        return

    with get_session() as session:
        active_profile, profile_data = get_active_profile_payload(session)
    score_result = compute_job_score(job, profile_data=profile_data)
    application = None
    contacts = []
    timeline = []
    if active_profile is not None:
        with get_session() as session:
            application = ApplicationRepository(session).get_by_job_and_profile(
                job.id, active_profile.id
            )
            if application is not None:
                contacts = get_application_contacts(session, application.id)
                timeline = get_application_timeline(session, application.id)

    title_col, action_col1, action_col2, action_col3, action_col4 = st.columns([4, 1, 1, 1, 1])
    title_col.subheader(f"{job.title} · {job.company}")
    if job.source_url:
        action_col1.link_button("Ouvrir URL", job.source_url, use_container_width=True)
    if action_col2.button("Creer ATS", use_container_width=True):
        if active_profile is None:
            st.error("Aucun profil actif.")
        else:
            try:
                with get_session() as session:
                    application = ensure_application(
                        session, job_id=job.id, profile_id=active_profile.id
                    )
            except Exception as exc:
                LOGGER.exception("ATS creation failed", extra={"job_id": job.id})
                st.error("Creation du dossier ATS impossible.")
                st.exception(exc)
            else:
                st.success(f"Dossier ATS cree: #{application.id}")
                st.rerun()
    if action_col3.button("Generer pack", use_container_width=True):
        if profile_data is None:
            st.error("Aucun profil disponible.")
        else:
            try:
                result = generate_application_pack(
                    job,
                    None,
                    Path("data/packs"),
                    profile_data=profile_data,
                )
            except Exception as exc:
                LOGGER.exception("Pack generation failed", extra={"job_id": job.id})
                st.error("Generation du pack impossible.")
                st.exception(exc)
            else:
                st.session_state["last_pack_dir"] = str(result.output_dir)
                st.success(f"Pack genere dans {result.output_dir}")
    if action_col4.button("Postuler assiste", use_container_width=True):
        st.session_state["current_page"] = "postuler"
        st.rerun()

    if st.button("Marquer applied"):
        try:
            with get_session() as session:
                if application is not None:
                    update_application_stage(
                        session,
                        application_id=application.id,
                        stage=ApplicationStage.APPLIED,
                        note="Offre marquee comme applied depuis le detail",
                    )
                else:
                    mark_job_applied(session, int(job.id))
        except Exception as exc:
            LOGGER.exception("Failed to update job status", extra={"job_id": job.id})
            st.error("Impossible de mettre a jour le statut.")
            st.exception(exc)
        else:
            st.success("Offre marquee comme applied.")

    info_col1, info_col2, info_col3 = st.columns(3)
    info_col1.metric("Statut", job.status.value)
    info_col2.metric("Localisation", job.location or "N/A")
    info_col3.metric("Score", score_result.score if score_result else "N/A")
    if active_profile is not None:
        st.caption(f"Profil actif: {active_profile.name}")
    if application is not None:
        st.caption(f"Candidature ATS: #{application.id} · stage `{application.stage.value}`")

    st.write(job.description or "Description non renseignee.")
    if score_result:
        st.caption("Explication du score")
        for reason in score_result.reasons:
            st.write(f"- {reason.label} ({reason.impact:+.1f})")
            st.caption(reason.evidence)

    st.divider()
    st.subheader("Workflow ATS")
    if application is None:
        st.info("Aucune candidature ATS pour cette offre et ce profil.")
    else:
        left, right = st.columns([2, 1])
        with left:
            with st.form("ats-stage-form"):
                stage = st.selectbox(
                    "Stage",
                    options=[item.value for item in ApplicationStage],
                    index=[item.value for item in ApplicationStage].index(
                        application.stage.value
                    ),
                )
                next_step = st.text_input(
                    "Prochaine action",
                    value=application.next_step or "",
                )
                next_step_due_at = st.date_input(
                    "Echeance",
                    value=(
                        application.next_step_due_at.date()
                        if application.next_step_due_at is not None
                        else None
                    ),
                )
                outcome_reason = st.text_input(
                    "Motif / issue",
                    value=application.outcome_reason or "",
                )
                note = st.text_area("Note de transition")
                submitted = st.form_submit_button(
                    "Mettre a jour le workflow", use_container_width=True
                )
            if submitted:
                try:
                    with get_session() as session:
                        update_application_stage(
                            session,
                            application_id=application.id,
                            stage=ApplicationStage(stage),
                            note=note or None,
                            next_step=next_step or None,
                            next_step_due_at=(
                                None
                                if next_step_due_at is None
                                else datetime.combine(
                                    next_step_due_at,
                                    time.min,
                                    tzinfo=timezone.utc,
                                )
                            ),
                            outcome_reason=outcome_reason or None,
                        )
                except AtsError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    LOGGER.exception("ATS stage update failed", extra={"job_id": job.id})
                    st.error("Mise a jour ATS impossible.")
                    st.exception(exc)
                else:
                    st.success("Workflow ATS mis a jour.")
                    st.rerun()

            with st.form("ats-event-form"):
                event_type = st.text_input("Type d'evenement", value="note")
                event_note = st.text_area("Note d'activite")
                event_submitted = st.form_submit_button(
                    "Ajouter un evenement", use_container_width=True
                )
            if event_submitted:
                if not event_note.strip():
                    st.warning("La note d'activite est obligatoire.")
                else:
                    try:
                        with get_session() as session:
                            add_application_event(
                                session,
                                application_id=application.id,
                                event_type=event_type.strip() or "note",
                                note=event_note.strip(),
                            )
                    except Exception as exc:
                        LOGGER.exception("ATS event creation failed", extra={"job_id": job.id})
                        st.error("Ajout d'evenement impossible.")
                        st.exception(exc)
                    else:
                        st.success("Evenement ATS ajoute.")
                        st.rerun()
        with right:
            with st.form("ats-contact-form"):
                full_name = st.text_input("Nom du contact")
                email = st.text_input("Email")
                phone = st.text_input("Telephone")
                role = st.text_input("Role")
                notes = st.text_area("Notes contact")
                contact_submitted = st.form_submit_button(
                    "Ajouter un contact", use_container_width=True
                )
            if contact_submitted:
                try:
                    with get_session() as session:
                        add_contact(
                            session,
                            application_id=application.id,
                            full_name=full_name,
                            email=email or None,
                            phone=phone or None,
                            role=role or None,
                            notes=notes or None,
                        )
                except AtsError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    LOGGER.exception("ATS contact creation failed", extra={"job_id": job.id})
                    st.error("Ajout de contact impossible.")
                    st.exception(exc)
                else:
                    st.success("Contact ajoute.")
                    st.rerun()

            st.caption("Contacts")
            if contacts:
                for contact in contacts:
                    with st.container(border=True):
                        st.write(f"**{contact.full_name}**")
                        st.caption(" | ".join(filter(None, [contact.role, contact.email, contact.phone])))
            else:
                st.info("Aucun contact.")

        st.caption("Timeline")
        if timeline:
            for event in timeline:
                with st.container(border=True):
                    st.write(f"**{event.event_type}** · {event.event_at.isoformat(timespec='minutes')}")
                    if event.note:
                        st.write(event.note)
                    if event.payload:
                        st.caption(str(event.payload))
        else:
            st.info("Aucun evenement ATS.")

    if st.session_state.get("last_pack_dir"):
        st.info(f"Dernier pack genere: {st.session_state['last_pack_dir']}")
