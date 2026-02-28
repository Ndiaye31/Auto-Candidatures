from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.tables import (
    ApplicationStatus,
    CandidateProfile,
    ContactStatus,
    EventStatus,
    JobStatus,
    User,
)


class JobCreate(BaseModel):
    title: str
    company: str
    location: str | None = None
    source_url: str | None = None
    source: str | None = None
    description: str | None = None
    status: JobStatus = JobStatus.NEW


class ApplicationCreate(BaseModel):
    job_id: int
    profile_id: int | None = None
    cover_letter_path: str | None = None
    resume_path: str | None = None
    status: ApplicationStatus = ApplicationStatus.DRAFT
    submitted_at: datetime | None = None
    notes: str | None = None


class ContactCreate(BaseModel):
    full_name: str
    job_id: int | None = None
    application_id: int | None = None
    email: str | None = None
    phone: str | None = None
    role: str | None = None
    status: ContactStatus = ContactStatus.NEW
    notes: str | None = None


class EventCreate(BaseModel):
    event_type: str
    job_id: int | None = None
    application_id: int | None = None
    contact_id: int | None = None
    status: EventStatus = EventStatus.PENDING
    payload: dict[str, Any] | None = None


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str


class CandidateProfileCreate(BaseModel):
    user_id: int
    name: str
    profile_yaml: str
    is_default: bool = False


class UserView(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool

    @classmethod
    def from_model(cls, user: User) -> "UserView":
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
        )


class CandidateProfileView(BaseModel):
    id: int
    user_id: int
    name: str
    slug: str
    profile_yaml: str
    is_default: bool

    @classmethod
    def from_model(cls, profile: CandidateProfile) -> "CandidateProfileView":
        return cls(
            id=profile.id,
            user_id=profile.user_id,
            name=profile.name,
            slug=profile.slug,
            profile_yaml=profile.profile_yaml,
            is_default=profile.is_default,
        )
