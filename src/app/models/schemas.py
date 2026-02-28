from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.tables import (
    ApplicationStatus,
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
