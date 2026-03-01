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
    get_selected_job_id,
    go_to_page,
    is_pack_ready_for_job,
    mark_job_applied,
    push_flash,
    render_job_summary_card,
)
from app.utils.logging import get_logger

LOGGER = get_logger("ui.detail")


def render() -> None:
    st.subheader("2. Generation pack")
    st.markdown(
        "<div class='section-hint'>Prepare les documents et le suivi ATS avant de passer au remplissage assiste.</div>",
        unsafe_allow_html=True,
    )
    job_id = get_selected_job_id()
    if not job_id:
        st.info("Aucune offre selectionnee. Reviens a l'etape 1 pour choisir une offre.")
        if st.button("Retour a la selection des offres", type="primary"):
            go_to_page("offres")
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

    render_job_summary_card(
        title=job.title,
        company=job.company,
        meta=(
            f"{job.location or 'Localisation non renseignee'} · "
            f"Score {score_result.score if score_result else 'N/A'} · "
            f"Profil {active_profile.name if active_profile is not None else 'indisponible'}"
        ),
        kicker="Preparation candidature",
    )

    status_col1, status_col2, status_col3, status_col4 = st.columns(4)
    status_col1.metric("Statut offre", job.status.value)
    status_col2.metric("Score", score_result.score if score_result else "N/A")
    status_col3.metric("Dossier ATS", f"#{application.id}" if application else "a creer")
    status_col4.metric("Pack", "pret" if is_pack_ready_for_job(job.id) else "a generer")

    primary_col1, primary_col2, primary_col3, primary_col4 = st.columns([1.3, 1, 1, 1])
    if primary_col1.button("Generer le pack", type="primary", use_container_width=True):
        if profile_data is None:
            st.error("Aucun profil disponible pour generer le pack.")
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
                st.session_state["last_pack_job_id"] = job.id
                st.session_state["last_pack_dir"] = str(result.output_dir)
                push_flash("success", f"Pack genere dans {result.output_dir}")
                st.rerun()
    if primary_col2.button("Creer ATS", use_container_width=True):
        if active_profile is None:
            st.error("Aucun profil actif.")
        else:
            try:
                with get_session() as session:
                    created_application = ensure_application(
                        session,
                        job_id=job.id,
                        profile_id=active_profile.id,
                    )
            except Exception as exc:
                LOGGER.exception("ATS creation failed", extra={"job_id": job.id})
                st.error("Creation du dossier ATS impossible.")
                st.exception(exc)
            else:
                push_flash("success", f"Dossier ATS pret: #{created_application.id}")
                st.rerun()
    if job.source_url:
        primary_col3.link_button("Ouvrir l'offre", job.source_url, use_container_width=True)
    else:
        primary_col3.caption("URL source indisponible")
    if primary_col4.button("Etape 3 · Postuler", use_container_width=True):
        go_to_page("postuler", selected_job_id=job.id)

    quick_col1, quick_col2, quick_col3 = st.columns(3)
    if quick_col1.button("Marquer applied", use_container_width=True):
        try:
            with get_session() as session:
                if application is not None:
                    update_application_stage(
                        session,
                        application_id=application.id,
                        stage=ApplicationStage.APPLIED,
                        note="Offre marquee comme applied depuis l'etape pack",
                    )
                else:
                    mark_job_applied(session, int(job.id))
        except Exception as exc:
            LOGGER.exception("Failed to update job status", extra={"job_id": job.id})
            st.error("Impossible de mettre a jour le statut.")
            st.exception(exc)
        else:
            push_flash("success", "Offre marquee comme applied.")
            st.rerun()
    quick_col2.caption(
        f"Dernier pack: {st.session_state['last_pack_dir']}"
        if is_pack_ready_for_job(job.id)
        else "Aucun pack genere pour cette offre."
    )
    quick_col3.caption("Aucune soumission automatique n'est effectuee.")

    tabs = st.tabs(["Pack et score", "Workflow ATS", "Contacts et timeline"])
    with tabs[0]:
        if st.session_state.get("last_pack_job_id") == job.id and st.session_state.get("last_pack_dir"):
            pack_dir = Path(st.session_state["last_pack_dir"])
            if pack_dir.exists():
                st.success(f"Pack disponible dans {pack_dir}")
                st.dataframe(
                    [
                        {"fichier": path.name, "taille_octets": path.stat().st_size}
                        for path in sorted(pack_dir.iterdir())
                        if path.is_file()
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
        else:
            st.info("Genere le pack pour produire les fichiers de candidature.")

        st.markdown("**Description de l'offre**")
        st.write(job.description or "Description non renseignee.")
        st.markdown("**Explication du score**")
        if score_result and score_result.reasons:
            for reason in score_result.reasons:
                st.write(f"- {reason.label} ({reason.impact:+.1f})")
                st.caption(reason.evidence)
        else:
            st.info("Aucune explication de score disponible.")

    with tabs[1]:
        if application is None:
            st.info("Aucun dossier ATS pour cette offre et ce profil.")
        else:
            with st.form("ats-stage-form"):
                stage = st.selectbox(
                    "Stage",
                    options=[item.value for item in ApplicationStage],
                    index=[item.value for item in ApplicationStage].index(
                        application.stage.value
                    ),
                )
                form_col1, form_col2 = st.columns(2)
                next_step = form_col1.text_input(
                    "Prochaine action",
                    value=application.next_step or "",
                )
                next_step_due_at = form_col2.date_input(
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
                    "Mettre a jour le workflow",
                    use_container_width=True,
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
                    push_flash("success", "Workflow ATS mis a jour.")
                    st.rerun()

            with st.form("ats-event-form"):
                event_type = st.text_input("Type d'evenement", value="note")
                event_note = st.text_area("Note d'activite")
                event_submitted = st.form_submit_button("Ajouter un evenement", use_container_width=True)
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
                        push_flash("success", "Evenement ATS ajoute.")
                        st.rerun()

    with tabs[2]:
        left, right = st.columns([1, 1.2])
        with left:
            if application is None:
                st.info("Cree d'abord le dossier ATS pour ajouter des contacts.")
            else:
                with st.form("ats-contact-form"):
                    full_name = st.text_input("Nom du contact")
                    email = st.text_input("Email")
                    phone = st.text_input("Telephone")
                    role = st.text_input("Role")
                    notes = st.text_area("Notes contact")
                    contact_submitted = st.form_submit_button(
                        "Ajouter un contact",
                        use_container_width=True,
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
                        push_flash("success", "Contact ajoute.")
                        st.rerun()
            st.markdown("**Contacts**")
            if contacts:
                for contact in contacts:
                    with st.container(border=True):
                        st.write(f"**{contact.full_name}**")
                        st.caption(" | ".join(filter(None, [contact.role, contact.email, contact.phone])))
            else:
                st.info("Aucun contact.")
        with right:
            st.markdown("**Timeline ATS**")
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
