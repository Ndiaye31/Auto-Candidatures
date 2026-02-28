from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import Session

from app.models.repositories import (
    ApplicationRepository,
    ContactRepository,
    EventRepository,
    JobRepository,
)
from app.models.tables import (
    Application,
    ApplicationStage,
    ApplicationStatus,
    Contact,
    ContactStatus,
    Event,
    EventStatus,
    JobStatus,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AtsError(ValueError):
    pass


STAGE_TO_STATUS = {
    ApplicationStage.SOURCED: ApplicationStatus.DRAFT,
    ApplicationStage.TO_REVIEW: ApplicationStatus.DRAFT,
    ApplicationStage.PACK_READY: ApplicationStatus.DRAFT,
    ApplicationStage.APPLIED: ApplicationStatus.SUBMITTED,
    ApplicationStage.SCREENING: ApplicationStatus.INTERVIEW,
    ApplicationStage.INTERVIEW_HR: ApplicationStatus.INTERVIEW,
    ApplicationStage.INTERVIEW_TECH: ApplicationStatus.INTERVIEW,
    ApplicationStage.CASE_STUDY: ApplicationStatus.INTERVIEW,
    ApplicationStage.FINAL_INTERVIEW: ApplicationStatus.INTERVIEW,
    ApplicationStage.OFFER: ApplicationStatus.OFFER,
    ApplicationStage.HIRED: ApplicationStatus.OFFER,
    ApplicationStage.REJECTED: ApplicationStatus.REJECTED,
    ApplicationStage.WITHDRAWN: ApplicationStatus.REJECTED,
}


@dataclass(slots=True)
class PipelineCard:
    application: Application
    job_title: str
    company: str
    stage: ApplicationStage
    next_step: str | None
    next_step_due_at: datetime | None


def ensure_application(
    session: Session,
    *,
    job_id: int,
    profile_id: int | None,
) -> Application:
    jobs = JobRepository(session)
    job = jobs.get(job_id)
    if job is None:
        raise AtsError("Offre introuvable.")

    applications = ApplicationRepository(session)
    existing = applications.get_by_job_and_profile(job_id, profile_id)
    if existing is not None:
        return existing

    application = applications.create(
        Application(
            job_id=job_id,
            profile_id=profile_id,
            status=ApplicationStatus.DRAFT,
            stage=ApplicationStage.SOURCED,
        )
    )
    jobs.update(job_id, status=JobStatus.REVIEWING)
    EventRepository(session).create(
        Event(
            job_id=job_id,
            application_id=application.id,
            event_type="application_created",
            status=EventStatus.PROCESSED,
            note="Creation du dossier ATS",
            event_at=utcnow(),
        )
    )
    return application


def update_application_stage(
    session: Session,
    *,
    application_id: int,
    stage: ApplicationStage,
    note: str | None = None,
    next_step: str | None = None,
    next_step_due_at: datetime | None = None,
    outcome_reason: str | None = None,
) -> Application:
    applications = ApplicationRepository(session)
    application = applications.get(application_id)
    if application is None:
        raise AtsError("Candidature introuvable.")

    updates: dict[str, object] = {
        "stage": stage,
        "status": STAGE_TO_STATUS[stage],
        "last_event_at": utcnow(),
        "next_step": next_step,
        "next_step_due_at": next_step_due_at,
        "outcome_reason": outcome_reason,
    }
    if stage == ApplicationStage.APPLIED and application.submitted_at is None:
        updates["submitted_at"] = utcnow()

    application = applications.update(application_id, **updates)
    if application is None:
        raise AtsError("Mise a jour impossible.")

    job_status = JobStatus.APPLIED if stage in {
        ApplicationStage.APPLIED,
        ApplicationStage.SCREENING,
        ApplicationStage.INTERVIEW_HR,
        ApplicationStage.INTERVIEW_TECH,
        ApplicationStage.CASE_STUDY,
        ApplicationStage.FINAL_INTERVIEW,
        ApplicationStage.OFFER,
        ApplicationStage.HIRED,
        ApplicationStage.REJECTED,
        ApplicationStage.WITHDRAWN,
    } else JobStatus.REVIEWING
    JobRepository(session).update(application.job_id, status=job_status)

    EventRepository(session).create(
        Event(
            job_id=application.job_id,
            application_id=application.id,
            event_type="stage_changed",
            status=EventStatus.PROCESSED,
            note=note or f"Stage ATS mis a jour: {stage.value}",
            payload={
                "stage": stage.value,
                "next_step": next_step,
                "outcome_reason": outcome_reason,
            },
            event_at=utcnow(),
        )
    )
    return application


def add_application_event(
    session: Session,
    *,
    application_id: int,
    event_type: str,
    note: str,
    payload: dict[str, object] | None = None,
) -> Event:
    application = ApplicationRepository(session).get(application_id)
    if application is None:
        raise AtsError("Candidature introuvable.")
    event = EventRepository(session).create(
        Event(
            job_id=application.job_id,
            application_id=application.id,
            event_type=event_type,
            status=EventStatus.PROCESSED,
            note=note,
            payload=payload,
            event_at=utcnow(),
        )
    )
    ApplicationRepository(session).update(
        application.id,
        last_event_at=event.event_at,
    )
    return event


def add_contact(
    session: Session,
    *,
    application_id: int,
    full_name: str,
    email: str | None = None,
    phone: str | None = None,
    role: str | None = None,
    notes: str | None = None,
) -> Contact:
    application = ApplicationRepository(session).get(application_id)
    if application is None:
        raise AtsError("Candidature introuvable.")
    if not full_name.strip():
        raise AtsError("Le nom du contact est obligatoire.")

    contact = ContactRepository(session).create(
        Contact(
            job_id=application.job_id,
            application_id=application.id,
            full_name=full_name.strip(),
            email=email.strip() if email else None,
            phone=phone.strip() if phone else None,
            role=role.strip() if role else None,
            status=ContactStatus.CONTACTED,
            notes=notes.strip() if notes else None,
        )
    )
    add_application_event(
        session,
        application_id=application.id,
        event_type="contact_added",
        note=f"Contact ajoute: {contact.full_name}",
        payload={
            "contact_id": contact.id,
            "role": contact.role,
        },
    )
    return contact


def get_pipeline_cards(
    session: Session, *, profile_id: int | None = None
) -> list[PipelineCard]:
    applications_repo = ApplicationRepository(session)
    jobs_repo = JobRepository(session)
    if profile_id is None:
        applications = applications_repo.list()
    else:
        applications = applications_repo.list_by_profile(profile_id)

    cards: list[PipelineCard] = []
    for application in applications:
        job = jobs_repo.get(application.job_id)
        if job is None:
            continue
        cards.append(
            PipelineCard(
                application=application,
                job_title=job.title,
                company=job.company,
                stage=application.stage,
                next_step=application.next_step,
                next_step_due_at=application.next_step_due_at,
            )
        )
    cards.sort(
        key=lambda card: (
            card.next_step_due_at is None,
            card.next_step_due_at or datetime.max.replace(tzinfo=timezone.utc),
            card.company.lower(),
        )
    )
    return cards


def get_application_contacts(session: Session, application_id: int) -> list[Contact]:
    application = ApplicationRepository(session).get(application_id)
    if application is None:
        return []
    statement_contacts = [
        contact
        for contact in ContactRepository(session).list_by_job(application.job_id)
        if contact.application_id == application_id
    ]
    return statement_contacts


def get_application_timeline(session: Session, application_id: int) -> list[Event]:
    return EventRepository(session).list_by_application(application_id)
