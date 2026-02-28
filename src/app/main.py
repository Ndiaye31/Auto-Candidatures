from __future__ import annotations

from datetime import datetime

import streamlit as st

from app.models.db import init_db


def _render_home() -> None:
    st.set_page_config(page_title="Job Application Assistant", layout="wide")
    st.title("Job Application Assistant")
    st.caption("V1 - Import, Scoring, Pack, Postuler (assisté)")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Offres", "0")
    col2.metric("Scorées", "0")
    col3.metric("Packs", "0")
    col4.metric("Pipeline", "0")

    st.divider()
    st.subheader("État")
    st.write(f"Horodatage: {datetime.utcnow().isoformat(timespec='seconds')}Z")
    st.info("DB initialisée. Prochaines pages: Import, Scoring, Postuler, Pipeline.")


def run() -> None:
    import streamlit.web.bootstrap as bootstrap
    from pathlib import Path

    file_path = str(Path(__file__).resolve())
    bootstrap.run(file_path, "", [], {})


if __name__ == "__main__":
    init_db()
    _render_home()
