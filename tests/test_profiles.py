from __future__ import annotations

from sqlmodel import Session

from app.models.db import create_db_engine, init_db
from app.models.repositories import CandidateProfileRepository
from app.services.profiles import (
    ProfileError,
    create_profile,
    ensure_default_profile,
    list_profiles,
    select_profile,
)


def test_ensure_default_profile_creates_one_when_missing() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        profile = ensure_default_profile(session)
        profiles = list_profiles(session)

    assert profile.is_default is True
    assert len(profiles) == 1
    assert profiles[0].name == "Profil principal"


def test_create_profile_validates_yaml() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        ensure_default_profile(session)
        try:
            create_profile(session, name="Invalide", profile_yaml=":::")
        except ProfileError:
            pass
        else:
            raise AssertionError("create_profile should reject invalid YAML")


def test_create_and_select_multiple_profiles() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        ensure_default_profile(session)
        second_profile = create_profile(
            session,
            name="Data profile",
            profile_yaml="identity:\n  full_name: Carol Martin\nskills:\n  - Python\n",
            is_default=False,
        )
        selected = select_profile(session, profile_id=second_profile.id)
        profiles = CandidateProfileRepository(session).list_profiles()

    assert selected is not None
    assert selected.id == second_profile.id
    assert profiles[0].id == second_profile.id
    assert profiles[0].is_default is True
