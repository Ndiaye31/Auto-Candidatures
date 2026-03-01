from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import yaml

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.models.db import get_session, init_db  # noqa: E402
from app.models.repositories import JobRepository  # noqa: E402
from app.services.import_offres import sync_jobs_from_default_alerts_excel  # noqa: E402
from app.services.profiles import (  # noqa: E402
    ProfileError,
    create_profile,
    ensure_default_profile,
    list_profiles,
    select_profile,
)
from app.ui.components import (  # noqa: E402
    get_active_profile,
    get_active_profile_payload,
    get_default_profile_path,
    get_selected_job_id,
    list_jobs_with_score,
    render_app_styles,
    render_flash,
    render_workflow_header,
    set_current_page,
)
from app.ui.pages import (  # noqa: E402
    page_import_offres,
    page_offers,
    page_offer_detail,
    page_pipeline,
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


def _render_profiles_sidebar() -> None:
    import streamlit as st

    with get_session() as session:
        ensure_default_profile(session)
        profiles = list_profiles(session)
        active_profile = get_active_profile(session)

    st.sidebar.subheader("Profils")
    if profiles:
        selected_profile_name = st.sidebar.selectbox(
            "Profil actif",
            options=[profile.id for profile in profiles],
            index=next(
                (
                    idx
                    for idx, profile in enumerate(profiles)
                    if active_profile is not None and profile.id == active_profile.id
                ),
                0,
            ),
            format_func=lambda profile_id: next(
                profile.name for profile in profiles if profile.id == profile_id
            ),
        )
        if active_profile is None or selected_profile_name != active_profile.id:
            with get_session() as session:
                selected = select_profile(session, profile_id=int(selected_profile_name))
            if selected is not None:
                st.session_state["active_profile_id"] = selected.id
                st.rerun()

    with st.sidebar.expander("Nouveau profil"):
        with st.form("new-profile-form"):
            profile_name = st.text_input("Nom du profil")
            yaml_seed = {"identity": {"full_name": "", "email": ""}}
            profile_yaml = st.text_area(
                "YAML du profil",
                value=yaml.safe_dump(yaml_seed, allow_unicode=True, sort_keys=False),
                height=220,
            )
            set_default = st.checkbox("Definir comme profil actif", value=True)
            submitted = st.form_submit_button("Creer le profil", use_container_width=True)
        if submitted:
            try:
                with get_session() as session:
                    profile = create_profile(
                        session,
                        name=profile_name,
                        profile_yaml=profile_yaml,
                        is_default=set_default,
                    )
                st.session_state["active_profile_id"] = profile.id
                st.sidebar.success("Profil cree.")
                st.rerun()
            except ProfileError as exc:
                st.sidebar.error(str(exc))


def _render_home() -> None:
    import streamlit as st

    st.set_page_config(page_title="Job Application Assistant", layout="wide")
    render_app_styles()
    try:
        init_db()
    except Exception as exc:
        LOGGER.exception("Database initialization failed")
        st.error("Initialisation de la base impossible.")
        st.exception(exc)
        return

    st.title("Job Application Assistant")
    st.caption("Workflow guide: selection offre, generation pack, postuler assiste. Aucun auto-submit.")
    _render_profiles_sidebar()

    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "offres"
    if "workflow_step" not in st.session_state:
        st.session_state["workflow_step"] = (
            st.session_state["current_page"]
            if st.session_state["current_page"] in {"offres", "detail", "postuler"}
            else "offres"
        )

    sidebar_primary = st.sidebar.radio(
        "Workflow principal",
        options=["offres", "detail", "postuler"],
        index=["offres", "detail", "postuler"].index(st.session_state["workflow_step"]),
        format_func=lambda value: {
            "offres": "1. Selection offre",
            "detail": "2. Generation pack",
            "postuler": "3. Postuler assiste",
        }[value],
    )
    if sidebar_primary != st.session_state["workflow_step"]:
        st.session_state["workflow_step"] = sidebar_primary
        st.session_state["current_page"] = sidebar_primary
    elif st.session_state["current_page"] in {"offres", "detail", "postuler"}:
        st.session_state["current_page"] = sidebar_primary
    with st.sidebar.expander("Outils secondaires", expanded=False):
        if st.button("Import offres", use_container_width=True):
            set_current_page("import")
            st.rerun()
        if st.button("Pipeline ATS", use_container_width=True):
            set_current_page("pipeline")
            st.rerun()

    try:
        with get_session() as session:
            active_profile, profile_data = get_active_profile_payload(session)
            profile_id = active_profile.id if active_profile is not None else None
            sync_status, sync_result = sync_jobs_from_default_alerts_excel(
                session,
                profile_id=profile_id,
            )
            jobs = list_jobs_with_score(session, profile_data=profile_data)
            selected_job_id = get_selected_job_id()
            selected_job = (
                JobRepository(session).get(selected_job_id)
                if selected_job_id is not None
                else None
            )
    except Exception as exc:
        LOGGER.exception("Failed to load jobs")
        st.error("Chargement des offres impossible.")
        st.exception(exc)
        return

    if active_profile is not None:
        st.sidebar.info(f"Profil actif: {active_profile.name}")
    else:
        profile_path = get_default_profile_path()
        if profile_path is None:
            st.sidebar.warning("Aucun profil actif et aucun profile.yaml detecte.")
        else:
            st.sidebar.success(f"Profil fichier charge: {profile_path}")
    if sync_result is not None:
        st.sidebar.caption(
            f"Sync alertes: {sync_result.created} nouvelles, {sync_result.skipped} ignorees, {sync_result.errors} erreurs"
        )
    elif sync_status.exists:
        st.sidebar.caption("Sync alertes: aucune modification detectee")

    render_flash()
    render_workflow_header(st.session_state["current_page"], selected_job=selected_job)

    primary_actions = st.columns([1, 1, 1, 2])
    if primary_actions[0].button("Etape 1 · Offres", use_container_width=True):
        st.session_state["workflow_step"] = "offres"
        set_current_page("offres")
        st.rerun()
    if primary_actions[1].button("Etape 2 · Pack", use_container_width=True):
        st.session_state["workflow_step"] = "detail"
        set_current_page("detail")
        st.rerun()
    if primary_actions[2].button("Etape 3 · Postuler", use_container_width=True):
        st.session_state["workflow_step"] = "postuler"
        set_current_page("postuler")
        st.rerun()
    primary_actions[3].caption(
        "Navigation principale claire. Les outils d'import et le pipeline ATS restent disponibles dans la sidebar."
    )

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
        page = st.session_state["current_page"]
        if page == "import":
            page_import_offres.render()
        elif page == "offres":
            page_offers.render()
        elif page == "detail":
            page_offer_detail.render()
        elif page == "pipeline":
            page_pipeline.render()
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
