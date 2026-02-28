from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import yaml

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.models.db import get_session, init_db  # noqa: E402
from app.services.auth import (  # noqa: E402
    AuthError,
    authenticate_user,
    create_profile,
    get_authenticated_context,
    list_profiles,
    register_user,
    select_profile,
)
from app.ui.components import (  # noqa: E402
    get_active_profile,
    get_active_profile_payload,
    get_current_user,
    get_default_profile_path,
    list_jobs_with_score,
)
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


def _logout() -> None:
    import streamlit as st

    keys_to_clear = [
        "auth_user_id",
        "active_profile_id",
        "selected_job_id",
        "current_page",
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]


def _render_auth_sidebar() -> bool:
    import streamlit as st

    st.sidebar.subheader("Authentification")
    with get_session() as session:
        current_user = get_current_user(session)

    if current_user is None:
        auth_mode = st.sidebar.radio("Acces", ["Connexion", "Inscription"])
        if auth_mode == "Connexion":
            with st.sidebar.form("login-form"):
                email = st.text_input("Email")
                password = st.text_input("Mot de passe", type="password")
                submitted = st.form_submit_button("Se connecter", use_container_width=True)
            if submitted:
                try:
                    with get_session() as session:
                        user = authenticate_user(
                            session, email=email, password=password
                        )
                        context = get_authenticated_context(session, user_id=user.id)
                    st.session_state["auth_user_id"] = user.id
                    st.session_state["active_profile_id"] = (
                        context.active_profile.id if context and context.active_profile else None
                    )
                    st.sidebar.success(f"Connecte: {user.full_name}")
                    st.rerun()
                except AuthError as exc:
                    st.sidebar.error(str(exc))
        else:
            with st.sidebar.form("register-form"):
                full_name = st.text_input("Nom complet")
                email = st.text_input("Email")
                password = st.text_input("Mot de passe", type="password")
                submitted = st.form_submit_button("Creer le compte", use_container_width=True)
            if submitted:
                try:
                    with get_session() as session:
                        user = register_user(
                            session,
                            email=email,
                            password=password,
                            full_name=full_name,
                        )
                        context = get_authenticated_context(session, user_id=user.id)
                    st.session_state["auth_user_id"] = user.id
                    st.session_state["active_profile_id"] = (
                        context.active_profile.id if context and context.active_profile else None
                    )
                    st.sidebar.success("Compte cree et connecte.")
                    st.rerun()
                except AuthError as exc:
                    st.sidebar.error(str(exc))
        return False

    st.sidebar.success(f"Connecte: {current_user.full_name}")
    st.sidebar.caption(current_user.email)
    if st.sidebar.button("Se deconnecter", use_container_width=True):
        _logout()
        st.rerun()

    with get_session() as session:
        profiles = list_profiles(session, user_id=current_user.id)
        active_profile = get_active_profile(session, current_user.id)

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
                selected = select_profile(
                    session, user_id=current_user.id, profile_id=int(selected_profile_name)
                )
            if selected is not None:
                st.session_state["active_profile_id"] = selected.id
                st.rerun()

    with st.sidebar.expander("Nouveau profil"):
        with st.form("new-profile-form"):
            profile_name = st.text_input("Nom du profil")
            yaml_seed = {
                "identity": {
                    "full_name": current_user.full_name,
                    "email": current_user.email,
                }
            }
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
                        user_id=current_user.id,
                        name=profile_name,
                        profile_yaml=profile_yaml,
                        is_default=set_default,
                    )
                st.session_state["active_profile_id"] = profile.id
                st.sidebar.success("Profil cree.")
                st.rerun()
            except AuthError as exc:
                st.sidebar.error(str(exc))

    return True


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

    if not _render_auth_sidebar():
        st.info("Connecte-toi ou cree un compte pour acceder a l'application.")
        return

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

    try:
        with get_session() as session:
            active_profile, profile_data = get_active_profile_payload(session)
            jobs = list_jobs_with_score(session, profile_data=profile_data)
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
