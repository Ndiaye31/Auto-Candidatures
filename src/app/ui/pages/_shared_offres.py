from __future__ import annotations

import pandas as pd
import streamlit as st

from app.models.db import get_session
from app.ui.components import (
    get_active_profile_payload,
    get_selected_job_id,
    go_to_page,
    list_jobs_with_score,
    render_job_summary_card,
)
from app.utils.logging import get_logger

LOGGER = get_logger("ui.offres")
PAGE_SIZE = 10


def render() -> None:
    st.subheader("1. Selection offre")
    st.markdown(
        "<div class='section-hint'>Filtre, compare puis selectionne une offre pour lancer le reste du workflow.</div>",
        unsafe_allow_html=True,
    )
    try:
        with get_session() as session:
            active_profile, profile_data = get_active_profile_payload(session)
            jobs = list_jobs_with_score(session, profile_data=profile_data)
    except Exception as exc:
        LOGGER.exception("Failed to load offers")
        st.error("Impossible de charger les offres.")
        st.exception(exc)
        return

    if active_profile is None:
        st.warning("Aucun profil actif en base. Les scores peuvent etre incomplets.")
    else:
        st.caption(f"Profil utilise pour le score: {active_profile.name}")

    with st.expander("Filtres et recherche", expanded=True):
        company_options = sorted({job["company"] for job in jobs})
        status_options = sorted({job["status"] for job in jobs})
        filter_col1, filter_col2, filter_col3 = st.columns([2, 2, 1])
        company_filter = filter_col1.multiselect("Entreprise", company_options)
        status_filter = filter_col2.multiselect("Statut", status_options)
        min_score = filter_col3.slider("Score min", 0, 100, 0)
        search = st.text_input("Recherche", placeholder="Titre, entreprise, stack, description...")

    filtered_jobs = []
    search_token = search.lower().strip()
    for item in jobs:
        haystack = " ".join(
            [
                item["title"],
                item["company"],
                item["location"],
                item["source"],
                item["job"].description or "",
            ]
        ).lower()
        if company_filter and item["company"] not in company_filter:
            continue
        if status_filter and item["status"] not in status_filter:
            continue
        if item["score"] is not None and item["score"] < min_score:
            continue
        if search_token and search_token not in haystack:
            continue
        filtered_jobs.append(item)

    if not filtered_jobs:
        st.info("Aucune offre ne correspond aux filtres actuels.")
        return

    summary_col1, summary_col2, summary_col3 = st.columns(3)
    summary_col1.metric("Resultats", len(filtered_jobs))
    summary_col2.metric("Scorées", sum(1 for item in filtered_jobs if item["score"] is not None))
    summary_col3.metric("Avec ATS", sum(1 for item in filtered_jobs if item["application_id"]))

    total_pages = max(1, (len(filtered_jobs) + PAGE_SIZE - 1) // PAGE_SIZE)
    page_key = "offers_page_index"
    current_page = st.number_input(
        "Page",
        min_value=1,
        max_value=total_pages,
        value=min(int(st.session_state.get(page_key, 1)), total_pages),
        step=1,
        key=page_key,
    )
    start = (int(current_page) - 1) * PAGE_SIZE
    page_rows = filtered_jobs[start : start + PAGE_SIZE]

    selected_job_id = get_selected_job_id()
    table_rows = [
        {
            "choisir": item["id"] == selected_job_id,
            "id": item["id"],
            "titre": item["title"],
            "entreprise": item["company"],
            "lieu": item["location"] or "N/A",
            "score": item["score"] if item["score"] is not None else -1,
            "statut": item["status"],
            "stage_ats": item["application_stage"] or "non cree",
        }
        for item in page_rows
    ]
    editor_df = pd.DataFrame(table_rows)
    edited = st.data_editor(
        editor_df,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "choisir": st.column_config.CheckboxColumn("Selection"),
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "titre": st.column_config.TextColumn("Titre", disabled=True, width="large"),
            "entreprise": st.column_config.TextColumn("Entreprise", disabled=True),
            "lieu": st.column_config.TextColumn("Lieu", disabled=True),
            "score": st.column_config.NumberColumn("Score", disabled=True, format="%d"),
            "statut": st.column_config.TextColumn("Statut", disabled=True),
            "stage_ats": st.column_config.TextColumn("Stage ATS", disabled=True),
        },
    )

    chosen_ids = edited.loc[edited["choisir"], "id"].tolist()
    if len(chosen_ids) > 1:
        st.warning("Selectionne une seule offre a la fois pour garder un workflow clair.")

    action_col1, action_col2, action_col3 = st.columns([1, 1, 2])
    if action_col1.button("Valider la selection", type="primary", use_container_width=True):
        if len(chosen_ids) != 1:
            st.warning("Choisis exactement une offre dans le tableau.")
        else:
            go_to_page("detail", selected_job_id=int(chosen_ids[0]))
    if action_col2.button("Ouvrir l'etape 2", use_container_width=True):
        if selected_job_id is None:
            st.info("Selectionne d'abord une offre dans le tableau.")
        else:
            go_to_page("detail")
    action_col3.caption(
        f"Affichage {start + 1} à {min(start + PAGE_SIZE, len(filtered_jobs))} sur {len(filtered_jobs)}."
    )

    selected_item = next(
        (item for item in filtered_jobs if item["id"] == selected_job_id),
        None,
    )
    if selected_item is not None:
        render_job_summary_card(
            title=selected_item["title"],
            company=selected_item["company"],
            meta=(
                f"{selected_item['location'] or 'Localisation non renseignee'} · "
                f"Score {selected_item['score'] if selected_item['score'] is not None else 'N/A'} · "
                f"Stage ATS {selected_item['application_stage'] or 'non cree'}"
            ),
        )
        preview_tabs = st.tabs(["Resume", "Score", "Actions"])
        with preview_tabs[0]:
            st.write(selected_item["job"].description or "Description non renseignee.")
        with preview_tabs[1]:
            if selected_item["score_reasons"]:
                for reason in selected_item["score_reasons"][:6]:
                    st.write(f"- {reason.label}")
                    st.caption(reason.evidence)
            else:
                st.info("Aucune explication de score disponible pour cette offre.")
        with preview_tabs[2]:
            action_preview_col1, action_preview_col2 = st.columns(2)
            if action_preview_col1.button(
                "Passer a la generation du pack",
                type="primary",
                use_container_width=True,
                key="go-detail-selected",
            ):
                go_to_page("detail", selected_job_id=selected_item["id"])
            if action_preview_col2.button(
                "Passer au postuler assiste",
                use_container_width=True,
                key="go-postuler-selected",
            ):
                go_to_page("postuler", selected_job_id=selected_item["id"])
    else:
        st.info("Aucune offre active. Selectionne une ligne puis valide la selection.")
