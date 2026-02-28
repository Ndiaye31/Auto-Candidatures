from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from app.models.db import get_session
from app.models.repositories import JobRepository
from app.services.extraction_dom import CANONICAL_RULES, FieldCandidate, map_form_fields
from app.ui.components import (
    apply_saved_mapping,
    field_candidates_to_rows,
    get_default_profile_path,
    get_domain_key,
    mark_job_applied,
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
    st.title("Postuler (assiste)")
    job_id = st.session_state.get("selected_job_id")
    if not job_id:
        st.info("Choisis d'abord une offre depuis la page Offres ou Detail.")
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

    profile_path = get_default_profile_path()
    if profile_path is None:
        st.error("Aucun profile.yaml disponible pour proposer des valeurs.")
        return

    st.subheader(f"{job.title} · {job.company}")
    domain_key = st.text_input("Site / domaine", value=get_domain_key(job.source_url))
    html = st.text_area(
        "HTML du formulaire",
        height=240,
        placeholder="<form>...</form>",
        key=f"html-form-{job.id}",
    )

    col1, col2, col3 = st.columns(3)
    if job.source_url:
        col1.link_button("Ouvrir URL", job.source_url, use_container_width=True)
    if col2.button("Marquer applied", use_container_width=True):
        try:
            with get_session() as session:
                mark_job_applied(session, int(job.id))
        except Exception as exc:
            LOGGER.exception("Failed to update job status", extra={"job_id": job.id})
            st.error("Impossible de mettre a jour le statut.")
            st.exception(exc)
        else:
            st.success("Offre marquee comme applied.")
    col3.caption("Auto-submit interdit: cette page n'envoie rien.")

    detect_clicked = st.button("Detecter les champs", type="primary")
    if detect_clicked and not html.strip():
        st.warning("Colle d'abord le HTML du formulaire.")
    elif detect_clicked and not domain_key.strip():
        st.warning("Le domaine/site doit etre renseigne pour reutiliser le mapping.")
    elif detect_clicked:
        try:
            detected = map_form_fields(html, Path(profile_path))
            st.session_state[f"mapping_rows_{job.id}"] = field_candidates_to_rows(
                apply_saved_mapping(domain_key.strip(), detected)
            )
        except Exception as exc:
            LOGGER.exception("Field detection failed", extra={"job_id": job.id})
            st.error("Detection des champs impossible.")
            st.exception(exc)
        else:
            st.success(f"{len(detected)} champ(s) detecte(s).")
            st.rerun()

    stored_rows = st.session_state.get(f"mapping_rows_{job.id}")
    if not stored_rows:
        st.info("Colle le HTML d'un formulaire puis clique sur 'Detecter les champs'.")
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
        column_config={
            "selector": st.column_config.TextColumn(disabled=True),
            "raw_label": st.column_config.TextColumn(disabled=True),
            "raw_name_or_id": st.column_config.TextColumn(disabled=True),
            "inferred_type": st.column_config.TextColumn(disabled=True),
            "canonical_key": st.column_config.SelectboxColumn(
                options=[""] + sorted(CANONICAL_RULES.keys())
            ),
            "proposed_value": st.column_config.TextColumn(),
            "confidence": st.column_config.NumberColumn(
                min_value=0.0, max_value=1.0, step=0.01, disabled=True
            ),
            "reasons": st.column_config.TextColumn(disabled=True),
        },
        key=f"editor-{job.id}",
    )

    action_col1, action_col2 = st.columns([1, 1])
    if action_col1.button("Sauvegarder mapping site", use_container_width=True):
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
                st.success(f"Mapping sauvegarde pour {domain_key.strip()}.")

    selected_selector = action_col2.selectbox(
        "Copier valeur pour",
        options=[""] + [row["selector"] for row in edited.to_dict(orient="records")],
        format_func=lambda value: "Selectionner un champ" if value == "" else value,
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
