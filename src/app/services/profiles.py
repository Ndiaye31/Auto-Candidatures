from __future__ import annotations

import re

from sqlmodel import Session

from app.models.repositories import CandidateProfileRepository
from app.models.tables import CandidateProfile
from app.services.profile_loader import dump_profile_payload, load_profile_payload


class ProfileError(ValueError):
    pass


DEFAULT_PROFILE_DATA = {
    "identity": {
        "full_name": "",
        "email": "",
        "phone": "",
        "location": "",
        "city": "",
    },
    "summary": "",
    "experience": {"current_title": "", "years_experience": 0},
    "skills": [],
    "achievements": [],
    "target_stack": [],
    "keywords": [],
    "preferences": {"remote": "preferred", "seniority": "mid"},
    "urls": {"linkedin": "", "github": ""},
    "salary": {"expected": ""},
    "availability": {"start_date": ""},
}
EXPECTED_PROFILE_KEYS = {
    "identity",
    "summary",
    "experience",
    "skills",
    "achievements",
    "target_stack",
    "keywords",
    "preferences",
    "urls",
    "salary",
    "availability",
}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "profil"


def build_default_profile_yaml() -> str:
    return dump_profile_payload(load_profile_payload(profile_data=DEFAULT_PROFILE_DATA))


def ensure_default_profile(session: Session) -> CandidateProfile:
    repository = CandidateProfileRepository(session)
    default_profile = repository.get_default()
    if default_profile is not None:
        return default_profile
    return repository.create(
        CandidateProfile(
            name="Profil principal",
            slug="profil-principal",
            profile_yaml=build_default_profile_yaml(),
            is_default=True,
        )
    )


def create_profile(
    session: Session,
    *,
    name: str,
    profile_yaml: str,
    is_default: bool = False,
) -> CandidateProfile:
    if not name.strip():
        raise ProfileError("Le nom du profil est obligatoire.")
    if not profile_yaml.strip():
        raise ProfileError("Le YAML du profil est obligatoire.")

    loaded_profile = load_profile_payload(profile_yaml=profile_yaml)
    if not isinstance(loaded_profile, dict):
        raise ProfileError("Le YAML du profil doit contenir un objet racine.")
    if not (set(loaded_profile) & EXPECTED_PROFILE_KEYS):
        raise ProfileError("Le YAML du profil ne contient aucune section attendue.")
    repository = CandidateProfileRepository(session)
    profile = repository.create(
        CandidateProfile(
            name=name.strip(),
            slug=_slugify(name.strip()),
            profile_yaml=profile_yaml.strip() + "\n",
            is_default=is_default,
        )
    )
    if is_default:
        repository.set_default(profile.id)
    return profile


def list_profiles(session: Session) -> list[CandidateProfile]:
    return CandidateProfileRepository(session).list_profiles()


def select_profile(session: Session, *, profile_id: int) -> CandidateProfile | None:
    repository = CandidateProfileRepository(session)
    profile = repository.get(profile_id)
    if profile is None:
        return None
    return repository.set_default(profile.id)
