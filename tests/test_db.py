from __future__ import annotations

from sqlmodel import Session, select

from app.models.db import SCHEMA_COMPONENT, SCHEMA_VERSION, create_db_engine, init_db
from app.models.repositories import (
    ApplicationRepository,
    ContactRepository,
    EventRepository,
    JobRepository,
)
from app.models.tables import (
    Application,
    ApplicationStatus,
    Contact,
    ContactStatus,
    Event,
    EventStatus,
    Job,
    JobStatus,
    SchemaVersion,
)


def test_init_db_creates_schema_version_for_in_memory_sqlite() -> None:
    engine = create_db_engine("sqlite://")

    version = init_db(engine)

    assert version.component == SCHEMA_COMPONENT
    assert version.version == SCHEMA_VERSION

    with Session(engine) as session:
        stored = session.exec(
            select(SchemaVersion).where(SchemaVersion.component == SCHEMA_COMPONENT)
        ).one()

    assert stored.version == SCHEMA_VERSION


def test_repositories_create_and_read_entities() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        jobs = JobRepository(session)
        applications = ApplicationRepository(session)
        contacts = ContactRepository(session)
        events = EventRepository(session)

        job = jobs.create(
            Job(
                title="Software Engineer",
                company="Acme",
                location="Paris",
                source_url="https://example.test/jobs/1",
                description="Backend role",
                status=JobStatus.NEW,
            )
        )
        application = applications.create(
            Application(
                job_id=job.id,
                cover_letter_path="generated/lm.md",
                resume_path="generated/cv.md",
                status=ApplicationStatus.SUBMITTED,
                notes="Submitted on company site",
            )
        )
        contact = contacts.create(
            Contact(
                job_id=job.id,
                application_id=application.id,
                full_name="Jane Recruiter",
                email="jane@example.test",
                status=ContactStatus.CONTACTED,
            )
        )
        event = events.create(
            Event(
                job_id=job.id,
                application_id=application.id,
                contact_id=contact.id,
                event_type="application_submitted",
                status=EventStatus.PROCESSED,
                payload={"source": "company-site"},
            )
        )

        assert jobs.get(job.id).company == "Acme"
        assert applications.get(application.id).status == ApplicationStatus.SUBMITTED
        assert contacts.get(contact.id).email == "jane@example.test"
        assert events.get(event.id).payload == {"source": "company-site"}

        assert [item.id for item in jobs.list()] == [job.id]
        assert [item.id for item in applications.list_by_job(job.id)] == [application.id]
        assert [item.id for item in contacts.list_by_job(job.id)] == [contact.id]
        assert [item.id for item in events.list_by_application(application.id)] == [
            event.id
        ]


def test_repositories_update_and_delete_entities() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        jobs = JobRepository(session)
        job = jobs.create(Job(title="Data Engineer", company="Acme"))

        updated = jobs.update(job.id, status=JobStatus.APPLIED, location="Remote")

        assert updated is not None
        assert updated.status == JobStatus.APPLIED
        assert updated.location == "Remote"

        deleted = jobs.delete(job.id)

        assert deleted is True
        assert jobs.get(job.id) is None
