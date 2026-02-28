from __future__ import annotations

from io import StringIO
from pathlib import Path

import streamlit as st

from app.models.db import get_session, init_db
from app.services.import_offres import (
    InvalidJobRowError,
    add_job,
    import_jobs_from_alerts_excel_path,
    import_jobs_from_csv,
)
from app.ui.components import get_active_profile_id
from app.utils.logging import get_logger

LOGGER = get_logger("ui.import_offres")


def _render_csv_import() -> None:
    st.subheader("Import CSV")
    st.caption("Colonnes attendues: title, company, location, url, description, source")

    uploaded_file = st.file_uploader("Fichier CSV", type=["csv"])
    if uploaded_file is None:
        return

    if st.button("Importer le CSV", type="primary"):
        try:
            with get_session() as session:
                result = import_jobs_from_csv(
                    session, StringIO(uploaded_file.getvalue().decode("utf-8-sig"))
                )
        except InvalidJobRowError as exc:
            st.error(str(exc))
        else:
            st.success(
                f"Import terminé: {result.created} créées, {result.skipped} ignorées."
            )


def _render_excel_alerts_import() -> None:
    st.subheader("Import Excel alertes")
    st.caption(
        "Format attendu: fichier d'alertes Indeed/HelloWork avec colonnes source "
        "du type `Titre du poste`, `URL de l'offre`, `Description`, `Statut`, "
        "`Type Candidature`, etc."
    )

    uploaded_file = st.file_uploader("Fichier Excel alertes", type=["xlsx"])
    if uploaded_file is None:
        return

    if st.button("Importer l'Excel alertes", type="primary"):
        temp_dir = Path("data/imports")
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / uploaded_file.name
        try:
            temp_path.write_bytes(uploaded_file.getbuffer())
            with get_session() as session:
                profile_id = get_active_profile_id(session)
                result = import_jobs_from_alerts_excel_path(
                    session,
                    temp_path,
                    profile_id=profile_id,
                )
        except InvalidJobRowError as exc:
            st.error(str(exc))
        except Exception as exc:
            LOGGER.exception("Excel alerts import failed")
            st.error("Import Excel impossible.")
            st.exception(exc)
        else:
            st.success(
                f"Import Excel terminé: {result.created} créées, {result.skipped} ignorées."
            )
            if profile_id is not None:
                st.caption("Le workflow ATS du profil actif a aussi été enrichi.")


def _render_manual_form() -> None:
    st.subheader("Ajout manuel")
    with st.form("manual-job-form"):
        title = st.text_input("Titre")
        company = st.text_input("Entreprise")
        location = st.text_input("Lieu")
        url = st.text_input("URL")
        source = st.text_input("Source")
        description = st.text_area("Description")
        submitted = st.form_submit_button("Ajouter l'offre")

    if not submitted:
        return

    try:
        with get_session() as session:
            _, created = add_job(
                session,
                title=title,
                company=company,
                location=location,
                url=url,
                source=source,
                description=description,
            )
    except InvalidJobRowError as exc:
        st.error(str(exc))
    else:
        if created:
            st.success("Offre ajoutée.")
        else:
            st.info("Offre déjà présente, aucune nouvelle ligne créée.")


def render() -> None:
    init_db()
    st.title("Import offres")
    _render_csv_import()
    st.divider()
    _render_excel_alerts_import()
    st.divider()
    _render_manual_form()
