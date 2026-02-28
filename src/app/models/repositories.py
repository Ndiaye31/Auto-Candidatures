from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, TypeVar

from sqlmodel import Session, SQLModel, select

from app.models.tables import (
    Application,
    CandidateProfile,
    Contact,
    Event,
    Job,
)

ModelT = TypeVar("ModelT", bound=SQLModel)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SQLModelRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        self.session.commit()
        self.session.refresh(instance)
        return instance

    def get(self, entity_id: int) -> ModelT | None:
        return self.session.get(self.model, entity_id)

    def list(self) -> list[ModelT]:
        statement = select(self.model).order_by(self.model.id)
        return list(self.session.exec(statement))

    def update(self, entity_id: int, **changes: object) -> ModelT | None:
        instance = self.get(entity_id)
        if instance is None:
            return None

        for field_name, value in changes.items():
            setattr(instance, field_name, value)

        if hasattr(instance, "updated_at"):
            setattr(instance, "updated_at", utcnow())

        self.session.add(instance)
        self.session.commit()
        self.session.refresh(instance)
        return instance

    def delete(self, entity_id: int) -> bool:
        instance = self.get(entity_id)
        if instance is None:
            return False

        self.session.delete(instance)
        self.session.commit()
        return True


class JobRepository(SQLModelRepository[Job]):
    model = Job

    def get_by_source_url(self, source_url: str) -> Job | None:
        statement = select(Job).where(Job.source_url == source_url)
        return self.session.exec(statement).first()


class CandidateProfileRepository(SQLModelRepository[CandidateProfile]):
    model = CandidateProfile

    def list_profiles(self) -> list[CandidateProfile]:
        statement = (
            select(CandidateProfile)
            .order_by(CandidateProfile.is_default.desc(), CandidateProfile.name)
        )
        return list(self.session.exec(statement))

    def get_default(self) -> CandidateProfile | None:
        statement = (
            select(CandidateProfile)
            .where(CandidateProfile.is_default.is_(True))
            .order_by(CandidateProfile.id.desc())
        )
        return self.session.exec(statement).first()

    def set_default(self, profile_id: int) -> CandidateProfile | None:
        profiles = self.list_profiles()
        target: CandidateProfile | None = None
        for profile in profiles:
            profile.is_default = profile.id == profile_id
            if hasattr(profile, "updated_at"):
                setattr(profile, "updated_at", utcnow())
            self.session.add(profile)
            if profile.id == profile_id:
                target = profile
        self.session.commit()
        if target is not None:
            self.session.refresh(target)
        return target


class ApplicationRepository(SQLModelRepository[Application]):
    model = Application

    def list_by_job(self, job_id: int) -> list[Application]:
        statement = select(Application).where(Application.job_id == job_id).order_by(
            Application.id
        )
        return list(self.session.exec(statement))


class ContactRepository(SQLModelRepository[Contact]):
    model = Contact

    def list_by_job(self, job_id: int) -> list[Contact]:
        statement = select(Contact).where(Contact.job_id == job_id).order_by(Contact.id)
        return list(self.session.exec(statement))


class EventRepository(SQLModelRepository[Event]):
    model = Event

    def list_by_application(self, application_id: int) -> list[Event]:
        statement = select(Event).where(
            Event.application_id == application_id
        ).order_by(Event.id)
        return list(self.session.exec(statement))
