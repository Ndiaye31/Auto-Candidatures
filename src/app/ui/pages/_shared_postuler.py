from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from app.browser.connectors import (
    describe_application_channel,
    infer_indeed_apply_kind,
    resolve_connector,
)
from app.browser.playwright_runtime import (
    PlaywrightSessionConfig,
    run_playwright_multi_step_flow,
)
from app.models.db import get_session
from app.models.repositories import ApplicationRepository, JobRepository
from app.models.tables import ApplicationStage
from app.services.ats import update_application_stage
from app.services.ats_learning import (
    list_top_external_ats,
    record_external_ats_domain,
    should_record_external_domain,
)
from app.services.extraction_dom import CANONICAL_RULES, FieldCandidate, map_form_fields
from app.ui.components import (
    apply_saved_mapping,
    field_candidates_to_rows,
    get_active_profile_payload,
    get_domain_key,
    get_selected_job_id,
    go_to_page,
    is_pack_ready_for_job,
    mark_job_applied,
    push_flash,
    render_job_summary_card,
    save_site_mapping,
)
from app.utils.logging import get_logger

LOGGER = get_logger("ui.postuler")


def _rows_to_candidates(rows: list[dict[str, object]]) -> list[FieldCandidate]:
    candidates: list[FieldCandidate] = []
    for row in rows:
        canonical_key = row.get("canonical_key")
        proposed_value = row.get("proposed_value")
        reasons = row.get("reasons", "")
        candidates.append(
            FieldCandidate(
                selector=str(row.get("selector", "")),
                raw_label=str(row.get("raw_label", "")),
                raw_name_or_id=str(row.get("raw_name_or_id", "")),
                inferred_type=str(row.get("inferred_type", "")),
                canonical_key=str(canonical_key) if canonical_key else None,
                proposed_value=str(proposed_value) if proposed_value else None,
                confidence=float(row.get("confidence", 0.0)),
                reasons=[
                    reason.strip()
                    for reason in str(reasons).split(" | ")
                    if reason.strip()
                ],
            )
        )
    return candidates


def render() -> None:
    st.subheader("3. Postuler (assiste)")
    st.markdown(
        "<div class='section-hint'>Navigation guidee, mapping conserve et validation manuelle finale. Aucun auto-submit.</div>",
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
        LOGGER.exception("Failed to load assisted apply page", extra={"job_id": job_id})
        st.error("Impossible de charger cette offre.")
        st.exception(exc)
        return
    if job is None:
        st.error("Offre introuvable.")
        return

    with get_session() as session:
        active_profile, profile_data = get_active_profile_payload(session)
        application = (
            None
            if active_profile is None
            else ApplicationRepository(session).get_by_job_and_profile(
                job.id, active_profile.id
            )
        )
    if profile_data is None:
        st.error("Aucun profil disponible pour proposer des valeurs.")
        return

    render_job_summary_card(
        title=job.title,
        company=job.company,
        meta=(
            f"{job.location or 'Localisation non renseignee'} · "
            f"Pack {'pret' if is_pack_ready_for_job(job.id) else 'non genere'} · "
            f"Profil {active_profile.name if active_profile is not None else 'indisponible'}"
        ),
        kicker="Execution assistee",
    )

    connector = resolve_connector(
        url=job.source_url,
        application_channel=(application.application_channel if application is not None else None),
        target_url=job.application_target_url,
        target_domain=job.application_target_domain,
    )
    channel_label = describe_application_channel(
        application.application_channel if application is not None else None
    )
    status_col1, status_col2, status_col3, status_col4 = st.columns(4)
    status_col1.metric("Canal", channel_label)
    status_col2.metric("Connecteur", connector.label)
    status_col3.metric("Pack", "pret" if is_pack_ready_for_job(job.id) else "a verifier")
    status_col4.metric("Soumission", "desactivee")

    action_col1, action_col2, action_col3 = st.columns([1, 1, 1.2])
    if job.source_url:
        action_col1.link_button("Ouvrir l'offre", job.source_url, use_container_width=True)
    if action_col2.button("Retour au pack", use_container_width=True):
        go_to_page("detail", selected_job_id=job.id)
    if action_col3.button("Marquer applied", use_container_width=True):
        try:
            with get_session() as session:
                if application is not None:
                    update_application_stage(
                        session,
                        application_id=application.id,
                        stage=ApplicationStage.APPLIED,
                        note="Offre marquee comme applied depuis Postuler assiste",
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

    tabs = st.tabs(["Navigation assistee", "Mapping formulaire"])

    with tabs[0]:
        st.info(
            "Le navigateur peut ouvrir la candidature, remplir les champs detectes, "
            "passer aux ecrans suivants puis s'arreter avant tout bouton final."
        )
        control_col1, control_col2, control_col3 = st.columns([1, 1, 2])
        headless = control_col1.checkbox("Headless", value=False)
        slow_mo_ms = control_col2.selectbox("Slow mode", options=[0, 250, 500, 1000], index=1)
        control_col3.caption(
            "Utilise le connecteur detecte automatiquement, memorise le domaine reel atteint "
            "et ne soumet jamais la candidature."
        )

        if st.button("Lancer la navigation assistee", type="primary", use_container_width=True):
            if not job.source_url:
                st.warning("Aucune URL source n'est disponible pour cette offre.")
            else:
                try:
                    with st.spinner("Navigation Playwright en cours..."):
                        runtime_result = run_playwright_multi_step_flow(
                            start_url=job.source_url,
                            profile_data=profile_data,
                            config=PlaywrightSessionConfig(
                                headless=headless,
                                slow_mo_ms=int(slow_mo_ms),
                            ),
                            connector=connector,
                        )
                except NotImplementedError:
                    st.error(
                        "Playwright n'a pas pu demarrer le navigateur dans ce contexte. "
                        "Relance l'application, puis reessaie."
                    )
                except Exception as exc:
                    LOGGER.exception("Playwright assisted navigation failed", extra={"job_id": job.id})
                    st.error("Navigation assistee impossible.")
                    st.exception(exc)
                else:
                    should_record_target = should_record_external_domain(
                        source_url=job.source_url,
                        target_url=runtime_result.resolved_url,
                        application_channel=(
                            application.application_channel if application is not None else None
                        ),
                    )
                    try:
                        with get_session() as session:
                            JobRepository(session).update(
                                job.id,
                                application_target_url=runtime_result.resolved_url,
                                application_target_domain=runtime_result.resolved_domain,
                            )
                            if should_record_target:
                                record_external_ats_domain(
                                    session,
                                    target_url=runtime_result.resolved_url,
                                )
                    except Exception:
                        LOGGER.exception(
                            "Failed to persist resolved target domain",
                            extra={"job_id": job.id},
                        )
                    st.session_state[f"browser_run_{job.id}"] = {
                        "connector": runtime_result.connector,
                        "resolved_connector": runtime_result.resolved_connector,
                        "apply_click_selector": runtime_result.apply_click_selector,
                        "stop_reason": runtime_result.automation_run.stop_reason,
                        "resolved_url": runtime_result.resolved_url,
                        "resolved_domain": runtime_result.resolved_domain,
                        "snapshot_path": (
                            str(runtime_result.snapshot_path)
                            if runtime_result.snapshot_path is not None
                            else None
                        ),
                        "steps": [
                            {
                                "step_index": step.snapshot.step_index + 1,
                                "url": step.snapshot.url,
                                "fields": len(step.snapshot.detected_fields),
                                "filled": len(step.filled_fields),
                                "clicked_next": "oui" if step.clicked_next else "non",
                                "stopped_before_submit": (
                                    "oui" if step.stopped_before_submit else "non"
                                ),
                            }
                            for step in runtime_result.automation_run.steps
                        ],
                    }
                    push_flash("success", "Session navigateur terminee sans submit.")
                    st.rerun()

        browser_run = st.session_state.get(f"browser_run_{job.id}")
        if browser_run:
            recap_col1, recap_col2, recap_col3 = st.columns(3)
            recap_col1.metric("Stop", browser_run["stop_reason"])
            recap_col2.metric("Domaine atteint", browser_run["resolved_domain"] or "N/A")
            recap_col3.metric("Connecteur reel", browser_run["resolved_connector"])
            if browser_run["resolved_url"]:
                st.caption(f"URL atteinte: {browser_run['resolved_url']}")
            if browser_run["apply_click_selector"]:
                st.caption(f"Bouton d'entree clique: {browser_run['apply_click_selector']}")
                if browser_run["connector"] == "indeed":
                    inferred_apply_kind = infer_indeed_apply_kind(
                        browser_run["apply_click_selector"]
                    )
                    if inferred_apply_kind == "easy_apply":
                        st.caption("Indeed: bouton detecte comme Easy Apply.")
                    elif inferred_apply_kind == "external":
                        st.caption("Indeed: bouton detecte comme redirection vers ATS externe.")
            if browser_run["snapshot_path"]:
                st.caption(f"Snapshot HTML: {browser_run['snapshot_path']}")
            st.dataframe(browser_run["steps"], use_container_width=True, hide_index=True)

            with get_session() as session:
                top_external_ats = list_top_external_ats(session, limit=5)
            if top_external_ats:
                st.caption("ATS externes frequents observes")
                st.dataframe(
                    [
                        {
                            "domain": stat.domain,
                            "connector": stat.connector_key,
                            "seen_count": stat.seen_count,
                            "sample_url": stat.sample_url,
                        }
                        for stat in top_external_ats
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

    with tabs[1]:
        domain_key = st.text_input(
            "Site / domaine pour le mapping",
            value=get_domain_key(job.application_target_url or job.source_url),
        )
        st.caption(
            "Conserve `canonical_key`, `confidence` et les valeurs proposees pour reutiliser le mapping plus tard."
        )
        html = st.text_area(
            "HTML du formulaire",
            height=220,
            placeholder="<form>...</form>",
            key=f"html-form-{job.id}",
        )

        detect_clicked = st.button("Detecter les champs", type="primary")
        if detect_clicked and not html.strip():
            st.warning("Colle d'abord le HTML du formulaire.")
        elif detect_clicked and not domain_key.strip():
            st.warning("Le domaine/site doit etre renseigne pour reutiliser le mapping.")
        elif detect_clicked:
            try:
                detected = map_form_fields(html, profile_data=profile_data)
                st.session_state[f"mapping_rows_{job.id}"] = field_candidates_to_rows(
                    apply_saved_mapping(domain_key.strip(), detected)
                )
            except Exception as exc:
                LOGGER.exception("Field detection failed", extra={"job_id": job.id})
                st.error("Detection des champs impossible.")
                st.exception(exc)
            else:
                push_flash("success", f"{len(detected)} champ(s) detecte(s).")
                st.rerun()

        stored_rows = st.session_state.get(f"mapping_rows_{job.id}")
        if not stored_rows:
            st.info("Colle le HTML du formulaire puis clique sur 'Detecter les champs'.")
            return

        editable_rows = []
        for row in stored_rows:
            editable_rows.append({**row, "reasons": " | ".join(row.get("reasons", []))})
        editor_df = pd.DataFrame(editable_rows)
        edited = st.data_editor(
            editor_df,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_order=[
                "raw_label",
                "proposed_value",
                "confidence",
                "canonical_key",
                "selector",
                "raw_name_or_id",
                "inferred_type",
                "reasons",
            ],
            column_config={
                "selector": st.column_config.TextColumn("Selector", disabled=True, width="medium"),
                "raw_label": st.column_config.TextColumn("Label", disabled=True, width="medium"),
                "raw_name_or_id": st.column_config.TextColumn("Name / ID", disabled=True, width="medium"),
                "inferred_type": st.column_config.TextColumn("Type", disabled=True),
                "canonical_key": st.column_config.SelectboxColumn(
                    "Canonical key",
                    options=[""] + sorted(CANONICAL_RULES.keys()),
                ),
                "proposed_value": st.column_config.TextColumn("Valeur proposee", width="large"),
                "confidence": st.column_config.NumberColumn(
                    "Confidence",
                    min_value=0.0,
                    max_value=1.0,
                    step=0.01,
                    disabled=True,
                    format="%.2f",
                ),
                "reasons": st.column_config.TextColumn("Raisons", disabled=True, width="large"),
            },
            key=f"editor-{job.id}",
        )

        editor_actions = st.columns([1, 1, 1.3])
        if editor_actions[0].button("Sauvegarder mapping", use_container_width=True):
            if not domain_key.strip():
                st.warning("Le domaine/site est obligatoire pour sauvegarder un mapping.")
            else:
                try:
                    candidates = _rows_to_candidates(edited.to_dict(orient="records"))
                    save_site_mapping(domain_key.strip(), candidates)
                    st.session_state[f"mapping_rows_{job.id}"] = field_candidates_to_rows(
                        candidates
                    )
                except Exception as exc:
                    LOGGER.exception("Saving site mapping failed", extra={"job_id": job.id})
                    st.error("Sauvegarde du mapping impossible.")
                    st.exception(exc)
                else:
                    push_flash("success", f"Mapping sauvegarde pour {domain_key.strip()}.")
                    st.rerun()

        selected_selector = editor_actions[1].selectbox(
            "Copier une valeur",
            options=[""] + [row["selector"] for row in edited.to_dict(orient="records")],
            format_func=lambda value: "Selectionner un champ" if value == "" else value,
        )
        editor_actions[2].caption(
            "Le tableau reste editable. Tu peux corriger la valeur proposee et reaffecter la canonical key avant copie manuelle."
        )

        if selected_selector:
            row = next(
                item
                for item in edited.to_dict(orient="records")
                if item["selector"] == selected_selector
            )
            value = row.get("proposed_value") or ""
            if not value:
                st.warning("Aucune valeur proposee pour ce champ. Edite-la manuellement.")
            st.code(value, language=None)
            st.caption("Copie manuelle uniquement. Aucun auto-submit n'est effectue.")
