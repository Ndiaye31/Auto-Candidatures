from __future__ import annotations

from sqlmodel import Session

from app.models.db import create_db_engine, init_db
from app.models.repositories import CandidateProfileRepository, UserRepository
from app.services.auth import (
    AuthError,
    authenticate_user,
    create_profile,
    get_authenticated_context,
    register_user,
    select_profile,
)


def test_register_user_creates_default_profile() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        user = register_user(
            session,
            email="alice@example.com",
            password="SuperSecret1",
            full_name="Alice Martin",
        )
        profiles = CandidateProfileRepository(session).list_by_user(user.id)

    assert user.email == "alice@example.com"
    assert len(profiles) == 1
    assert profiles[0].is_default is True
    assert "Alice Martin" in profiles[0].profile_yaml


def test_authenticate_user_rejects_invalid_password() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        register_user(
            session,
            email="bob@example.com",
            password="CorrectHorse1",
            full_name="Bob Martin",
        )
        try:
            authenticate_user(
                session,
                email="bob@example.com",
                password="wrong-password",
            )
        except AuthError as exc:
            assert "invalides" in str(exc)
        else:
            raise AssertionError("authenticate_user should reject a bad password")


def test_create_and_select_multiple_profiles() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        user = register_user(
            session,
            email="carol@example.com",
            password="SuperSecret1",
            full_name="Carol Martin",
        )
        second_profile = create_profile(
            session,
            user_id=user.id,
            name="Data profile",
            profile_yaml="identity:\n  full_name: Carol Martin\nskills:\n  - Python\n",
            is_default=False,
        )
        selected = select_profile(
            session, user_id=user.id, profile_id=second_profile.id
        )
        context = get_authenticated_context(
            session,
            user_id=user.id,
            profile_id=second_profile.id,
        )

    assert selected is not None
    assert selected.id == second_profile.id
    assert context is not None
    assert context.active_profile is not None
    assert context.active_profile.name == "Data profile"
