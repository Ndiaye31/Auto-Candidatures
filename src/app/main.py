from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.models.db import get_session, init_db  # noqa: E402
from app.ui.components import get_default_profile_path, list_jobs_with_score  # noqa: E402
from app.ui.pages import (  # noqa: E402
    page_offers,
    page_offer_detail,
    page_postuler_assiste,
)
from app.utils.logging import get_logger  # noqa: E402


LAUNCH_INSTRUCTIONS = (
    "Cette application est une interface Streamlit.\n"
    "Lance-la avec l'une de ces commandes:\n"
    "  streamlit run src/app/main.py\n"
    "  python -m streamlit run src/app/main.py\n"
    "  app"
)
LOGGER = get_logger("main")


def _is_streamlit_runtime() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


def _render_home() -> None:
    import streamlit as st

    st.set_page_config(page_title="Job Application Assistant", layout="wide")
    try:
        init_db()
    except Exception as exc:
        LOGGER.exception("Database initialization failed")
        st.error("Initialisation de la base impossible.")
        st.exception(exc)
        return

    st.title("Job Application Assistant")
    st.caption("UI assistee uniquement. Aucun auto-submit.")

    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "offres"

    page = st.sidebar.radio(
        "Pages",
        options=["offres", "detail", "postuler"],
        index=["offres", "detail", "postuler"].index(st.session_state["current_page"]),
        format_func=lambda value: {
            "offres": "Offres",
            "detail": "Detail offre",
            "postuler": "Postuler (assiste)",
        }[value],
    )
    st.session_state["current_page"] = page

    profile_path = get_default_profile_path()
    if profile_path is None:
        st.sidebar.warning("Aucun profile.yaml detecte.")
    else:
        st.sidebar.success(f"Profil charge: {profile_path}")

    try:
        with get_session() as session:
            jobs = list_jobs_with_score(session, profile_path)
    except Exception as exc:
        LOGGER.exception("Failed to load jobs")
        st.error("Chargement des offres impossible.")
        st.exception(exc)
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Offres", len(jobs))
    col2.metric("Scorées", sum(1 for item in jobs if item["score"] is not None))
    col3.metric("Applied", sum(1 for item in jobs if item["status"] == "applied"))
    col4.metric(
        "Horodatage",
        datetime.now(timezone.utc).isoformat(timespec="seconds").split("T")[1],
    )

    st.divider()
    try:
        if page == "offres":
            page_offers.render()
        elif page == "detail":
            page_offer_detail.render()
        else:
            page_postuler_assiste.render()
    except Exception as exc:
        LOGGER.exception("Page rendering failed", extra={"page": page})
        st.error("Une erreur est survenue pendant le rendu de la page.")
        st.exception(exc)


def run() -> None:
    raise SystemExit(LAUNCH_INSTRUCTIONS)


if __name__ == "__main__":
    if not _is_streamlit_runtime():
        raise SystemExit(LAUNCH_INSTRUCTIONS)
    _render_home()
