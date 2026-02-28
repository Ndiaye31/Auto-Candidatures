from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app.models.db import create_db_engine, init_db
from app.models.repositories import ApplicationRepository
from app.models.tables import ApplicationStage, ApplicationStatus, Job
from app.services.ats import (
    add_application_event,
    add_contact,
    ensure_application,
    get_application_contacts,
    get_application_timeline,
    get_pipeline_cards,
    update_application_stage,
)
from app.services.profiles import ensure_default_profile


def test_ensure_application_creates_single_ats_record() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        profile = ensure_default_profile(session)
        job = session.add(Job(title="Backend Engineer", company="Acme")) or None
        session.commit()
        job = session.get(Job, 1)

        first = ensure_application(session, job_id=job.id, profile_id=profile.id)
        second = ensure_application(session, job_id=job.id, profile_id=profile.id)

    assert first.id == second.id
    assert first.stage == ApplicationStage.SOURCED
    assert first.status == ApplicationStatus.DRAFT


def test_update_application_stage_updates_status_and_timeline() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        profile = ensure_default_profile(session)
        job = Job(title="Platform Engineer", company="Beta")
        session.add(job)
        session.commit()
        session.refresh(job)
        application = ensure_application(session, job_id=job.id, profile_id=profile.id)

        updated = update_application_stage(
            session,
            application_id=application.id,
            stage=ApplicationStage.INTERVIEW_HR,
            note="Screening valide",
            next_step="Entretien RH",
            next_step_due_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
        )
        timeline = get_application_timeline(session, application.id)

    assert updated.stage == ApplicationStage.INTERVIEW_HR
    assert updated.status == ApplicationStatus.INTERVIEW
    assert updated.next_step == "Entretien RH"
    assert timeline[0].event_type == "stage_changed"
    assert timeline[0].note == "Screening valide"


def test_add_contact_and_event_feed_pipeline() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        profile = ensure_default_profile(session)
        job = Job(title="Data Engineer", company="Gamma")
        session.add(job)
        session.commit()
        session.refresh(job)
        application = ensure_application(session, job_id=job.id, profile_id=profile.id)
        update_application_stage(
            session,
            application_id=application.id,
            stage=ApplicationStage.APPLIED,
            next_step="Relance recruteur",
            next_step_due_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        )

        contact = add_contact(
            session,
            application_id=application.id,
            full_name="Jane Recruiter",
            email="jane@example.com",
            role="Recruiter",
        )
        add_application_event(
            session,
            application_id=application.id,
            event_type="follow_up",
            note="Relance envoyee",
        )

        cards = get_pipeline_cards(session, profile_id=profile.id)
        contacts = get_application_contacts(session, application.id)
        stored_application = ApplicationRepository(session).get(application.id)

    assert contact.id is not None
    assert len(cards) == 1
    assert cards[0].stage == ApplicationStage.APPLIED
    assert cards[0].next_step == "Relance recruteur"
    assert len(contacts) == 1
    assert contacts[0].full_name == "Jane Recruiter"
    assert stored_application.last_event_at is not None
