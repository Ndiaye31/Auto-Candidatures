from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.tables import (
    ApplicationStatus,
    ApplicationStage,
    CandidateProfile,
    ContactStatus,
    EventStatus,
    JobStatus,
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
    stage: ApplicationStage = ApplicationStage.SOURCED
    submitted_at: datetime | None = None
    next_step: str | None = None
    next_step_due_at: datetime | None = None
    outcome_reason: str | None = None
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
    note: str | None = None
    payload: dict[str, Any] | None = None


class CandidateProfileCreate(BaseModel):
    name: str
    profile_yaml: str
    is_default: bool = False


class CandidateProfileView(BaseModel):
    id: int
    name: str
    slug: str
    profile_yaml: str
    is_default: bool

    @classmethod
    def from_model(cls, profile: CandidateProfile) -> "CandidateProfileView":
        return cls(
            id=profile.id,
            name=profile.name,
            slug=profile.slug,
            profile_yaml=profile.profile_yaml,
            is_default=profile.is_default,
        )
