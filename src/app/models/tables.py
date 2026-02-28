from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class Company(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    website: Optional[str] = None


class JobOffer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id")
    title: str
    location: Optional[str] = None
    contract_type: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    description_raw: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class JobOfferImport(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_type: str
    source_ref: str
    imported_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "ok"
    errors: Optional[str] = None


class CandidateProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    skills_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    experience_years: Optional[int] = None
    notes: Optional[str] = None


class Score(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_offer_id: int = Field(foreign_key="joboffer.id")
    candidate_profile_id: int = Field(foreign_key="candidateprofile.id")
    score_total: float
    score_breakdown_json: dict = Field(sa_column=Column(JSON))
    computed_at: datetime = Field(default_factory=datetime.utcnow)


class ApplicationPack(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_offer_id: int = Field(foreign_key="joboffer.id")
    candidate_profile_id: int = Field(foreign_key="candidateprofile.id")
    pack_path: str
    cv_path: str
    lm_path: str
    answers_json_path: str
    fields_csv_path: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class PipelineEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_offer_id: int = Field(foreign_key="joboffer.id")
    event_type: str
    payload_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
