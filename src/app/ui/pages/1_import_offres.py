from __future__ import annotations

from io import StringIO

import streamlit as st

from app.models.db import get_session, init_db
from app.services.import_offres import (
    InvalidJobRowError,
    add_job,
    import_jobs_from_csv,
)


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


def main() -> None:
    init_db()
    st.title("Import offres")
    _render_csv_import()
    st.divider()
    _render_manual_form()


main()
