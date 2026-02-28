from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, JSON, String
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(StrEnum):
    NEW = "new"
    REVIEWING = "reviewing"
    APPLIED = "applied"
    ARCHIVED = "archived"


class ApplicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    INTERVIEW = "interview"
    REJECTED = "rejected"
    OFFER = "offer"


class ApplicationStage(StrEnum):
    SOURCED = "sourced"
    TO_REVIEW = "to_review"
    PACK_READY = "pack_ready"
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW_HR = "interview_hr"
    INTERVIEW_TECH = "interview_tech"
    CASE_STUDY = "case_study"
    FINAL_INTERVIEW = "final_interview"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ContactStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    REPLIED = "replied"
    INACTIVE = "inactive"


class EventStatus(StrEnum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


class SchemaVersion(SQLModel, table=True):
    __tablename__ = "schema_versions"

    id: int | None = Field(default=None, primary_key=True)
    component: str = Field(index=True, unique=True)
    version: int
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)


class CandidateProfile(SQLModel, table=True):
    __tablename__ = "candidate_profiles"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    slug: str = Field(index=True)
    profile_yaml: str
    is_default: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    company: str = Field(index=True)
    location: str | None = None
    source_url: str | None = Field(
        default=None,
        sa_column=Column("source_url", String, unique=True, nullable=True),
    )
    source: str | None = None
    description: str | None = None
    status: JobStatus = Field(default=JobStatus.NEW, index=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)


class Application(SQLModel, table=True):
    __tablename__ = "applications"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id", index=True)
    profile_id: int | None = Field(
        default=None, foreign_key="candidate_profiles.id", index=True
    )
    cover_letter_path: str | None = None
    resume_path: str | None = None
    application_channel: str | None = None
    status: ApplicationStatus = Field(default=ApplicationStatus.DRAFT, index=True)
    stage: ApplicationStage = Field(default=ApplicationStage.SOURCED, index=True)
    submitted_at: datetime | None = None
    last_event_at: datetime | None = None
    next_step: str | None = None
    next_step_due_at: datetime | None = None
    outcome_reason: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)


class Contact(SQLModel, table=True):
    __tablename__ = "contacts"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int | None = Field(default=None, foreign_key="jobs.id", index=True)
    application_id: int | None = Field(
        default=None, foreign_key="applications.id", index=True
    )
    full_name: str
    email: str | None = None
    phone: str | None = None
    role: str | None = None
    status: ContactStatus = Field(default=ContactStatus.NEW, index=True)
    notes: str | None = None
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int | None = Field(default=None, foreign_key="jobs.id", index=True)
    application_id: int | None = Field(
        default=None, foreign_key="applications.id", index=True
    )
    contact_id: int | None = Field(default=None, foreign_key="contacts.id", index=True)
    event_type: str = Field(index=True)
    status: EventStatus = Field(default=EventStatus.PENDING, index=True)
    note: str | None = None
    payload: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    event_at: datetime = Field(default_factory=utcnow, nullable=False)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
