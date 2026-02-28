from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.models.db import get_session
from app.ui.components import get_active_profile_payload, list_jobs_with_score
from app.utils.logging import get_logger

LOGGER = get_logger("ui.offres")


def render() -> None:
    st.title("Offres")
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
        st.warning("Aucun profil actif en base. Les scores peuvent etre masques.")
    else:
        st.caption(f"Profil utilise pour le score: {active_profile.name}")

    company_options = sorted({job["company"] for job in jobs})
    status_options = sorted({job["status"] for job in jobs})

    col1, col2, col3 = st.columns([2, 2, 1])
    company_filter = col1.multiselect("Entreprise", company_options)
    status_filter = col2.multiselect("Statut", status_options)
    min_score = col3.slider("Score min", 0, 100, 0)
    search = st.text_input("Recherche", placeholder="titre, entreprise, stack...")

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

    st.caption(f"{len(filtered_jobs)} offre(s)")
    if not filtered_jobs:
        st.info("Aucune offre ne correspond aux filtres actuels.")
        return

    page_size = 10
    total_pages = max(1, (len(filtered_jobs) + page_size - 1) // page_size)
    current_page = st.number_input(
        "Page",
        min_value=1,
        max_value=total_pages,
        value=1,
        step=1,
    )
    start = (int(current_page) - 1) * page_size
    end = start + page_size
    st.caption(f"Affichage des offres {start + 1} à {min(end, len(filtered_jobs))}")

    for item in filtered_jobs[start:end]:
        with st.container(border=True):
            top_left, top_mid, top_right = st.columns([3, 1, 1])
            top_left.subheader(f"{item['title']} · {item['company']}")
            top_mid.metric("Score", item["score"] if item["score"] is not None else "N/A")
            top_right.write(f"Statut: `{item['status']}`")
            if item["application_stage"]:
                st.caption(f"Stage ATS: {item['application_stage']}")
            elif active_profile is not None:
                st.caption("Stage ATS: non cree")
            st.write(item["location"] or "Localisation non renseignee")
            if item["score_reasons"]:
                st.caption(
                    " | ".join(reason.label for reason in item["score_reasons"][:3])
                )
            if st.button("Voir detail", key=f"job-detail-{item['id']}"):
                st.session_state["selected_job_id"] = item["id"]
                st.session_state["current_page"] = "detail"
                st.rerun()
