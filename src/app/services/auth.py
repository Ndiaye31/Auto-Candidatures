from __future__ import annotations

from dataclasses import dataclass
from hashlib import pbkdf2_hmac, sha256
import hmac
import os
import re

from sqlmodel import Session

from app.models.repositories import CandidateProfileRepository, UserRepository
from app.models.tables import CandidateProfile, User
from app.services.profile_loader import dump_profile_payload, load_profile_payload


class AuthError(ValueError):
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


@dataclass(slots=True)
class AuthenticatedContext:
    user: User
    active_profile: CandidateProfile | None


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "profil"


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise AuthError("Le mot de passe doit contenir au moins 8 caracteres.")
    salt = os.urandom(16)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt_hex, digest_hex = password_hash.split(":", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    candidate = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(candidate, expected)


def build_default_profile_yaml(*, full_name: str, email: str) -> str:
    payload = load_profile_payload(profile_data=DEFAULT_PROFILE_DATA.copy())
    identity = dict(payload.get("identity", {}))
    identity["full_name"] = full_name
    identity["email"] = email
    payload["identity"] = identity
    return dump_profile_payload(payload)


def register_user(
    session: Session,
    *,
    email: str,
    password: str,
    full_name: str,
) -> User:
    normalized_email = _normalize_email(email)
    if not normalized_email:
        raise AuthError("L'email est obligatoire.")
    if not full_name.strip():
        raise AuthError("Le nom complet est obligatoire.")

    user_repository = UserRepository(session)
    if user_repository.get_by_email(normalized_email) is not None:
        raise AuthError("Un compte existe deja pour cet email.")

    user = user_repository.create(
        User(
            email=normalized_email,
            password_hash=hash_password(password),
            full_name=full_name.strip(),
        )
    )
    profile_repository = CandidateProfileRepository(session)
    profile_repository.create(
        CandidateProfile(
            user_id=user.id,
            name="Profil principal",
            slug="profil-principal",
            profile_yaml=build_default_profile_yaml(
                full_name=user.full_name,
                email=user.email,
            ),
            is_default=True,
        )
    )
    return user


def authenticate_user(session: Session, *, email: str, password: str) -> User:
    user = UserRepository(session).get_by_email(_normalize_email(email))
    if user is None or not user.is_active:
        raise AuthError("Identifiants invalides.")
    if not verify_password(password, user.password_hash):
        raise AuthError("Identifiants invalides.")
    return user


def create_profile(
    session: Session,
    *,
    user_id: int,
    name: str,
    profile_yaml: str,
    is_default: bool = False,
) -> CandidateProfile:
    if not name.strip():
        raise AuthError("Le nom du profil est obligatoire.")
    if not profile_yaml.strip():
        raise AuthError("Le YAML du profil est obligatoire.")

    load_profile_payload(profile_yaml=profile_yaml)
    repository = CandidateProfileRepository(session)
    profile = repository.create(
        CandidateProfile(
            user_id=user_id,
            name=name.strip(),
            slug=_slugify(name.strip()),
            profile_yaml=profile_yaml.strip() + "\n",
            is_default=is_default,
        )
    )
    if is_default:
        repository.set_default(profile.id, user_id)
    return profile


def list_profiles(session: Session, *, user_id: int) -> list[CandidateProfile]:
    return CandidateProfileRepository(session).list_by_user(user_id)


def select_profile(
    session: Session, *, user_id: int, profile_id: int
) -> CandidateProfile | None:
    repository = CandidateProfileRepository(session)
    profile = repository.get_for_user(profile_id, user_id)
    if profile is None:
        return None
    return repository.set_default(profile.id, user_id)


def get_authenticated_context(
    session: Session, *, user_id: int, profile_id: int | None = None
) -> AuthenticatedContext | None:
    user = UserRepository(session).get(user_id)
    if user is None or not user.is_active:
        return None

    profiles = CandidateProfileRepository(session)
    active_profile = None
    if profile_id is not None:
        active_profile = profiles.get_for_user(profile_id, user.id)
    if active_profile is None:
        active_profile = profiles.get_default_for_user(user.id)
    return AuthenticatedContext(user=user, active_profile=active_profile)
