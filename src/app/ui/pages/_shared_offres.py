from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.models.db import get_session
from app.ui.components import get_default_profile_path, list_jobs_with_score


def render() -> None:
    st.title("Offres")
    profile_path = get_default_profile_path()
    if profile_path is None:
        st.warning("Aucun profile.yaml detecte. Les scores sont masques.")
    else:
        st.caption(f"Profil utilise pour le score: {Path(profile_path)}")

    with get_session() as session:
        jobs = list_jobs_with_score(session, profile_path)

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
    for item in filtered_jobs:
        with st.container(border=True):
            top_left, top_mid, top_right = st.columns([3, 1, 1])
            top_left.subheader(f"{item['title']} · {item['company']}")
            top_mid.metric("Score", item["score"] if item["score"] is not None else "N/A")
            top_right.write(f"Statut: `{item['status']}`")
            st.write(item["location"] or "Localisation non renseignee")
            if item["score_reasons"]:
                st.caption(
                    " | ".join(reason.label for reason in item["score_reasons"][:3])
                )
            if st.button("Voir detail", key=f"job-detail-{item['id']}"):
                st.session_state["selected_job_id"] = item["id"]
                st.session_state["current_page"] = "detail"
                st.rerun()
