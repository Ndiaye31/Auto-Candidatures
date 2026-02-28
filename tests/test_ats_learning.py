from __future__ import annotations

from sqlmodel import Session

from app.models.db import create_db_engine, init_db
from app.models.repositories import AtsDomainStatRepository, JobRepository
from app.models.tables import Job
from app.services.ats_learning import (
    list_top_external_ats,
    normalize_domain,
    record_external_ats_domain,
    should_record_external_domain,
)


def test_normalize_domain_handles_urls_and_www() -> None:
    assert normalize_domain("https://www.jobs.lever.co/acme/backend") == "jobs.lever.co"


def test_record_external_ats_domain_counts_repeated_domains() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        first = record_external_ats_domain(
            session,
            target_url="https://boards.greenhouse.io/acme/jobs/123",
        )
        second = record_external_ats_domain(
            session,
            target_url="https://boards.greenhouse.io/acme/jobs/456",
        )
        top = list_top_external_ats(session, limit=5)

    assert first is not None
    assert second is not None
    assert second.seen_count == 2
    assert top[0].domain == "boards.greenhouse.io"
    assert top[0].connector_key == "greenhouse"


def test_should_record_external_domain_detects_redirects_and_external_channels() -> None:
    assert should_record_external_domain(
        source_url="https://fr.indeed.com/viewjob?jk=abc123",
        target_url="https://jobs.lever.co/acme/backend",
        application_channel="indeed_external",
    )
    assert not should_record_external_domain(
        source_url="https://fr.indeed.com/viewjob?jk=abc123",
        target_url="https://fr.indeed.com/viewjob?jk=abc123",
        application_channel="indeed_external",
    )
    assert not should_record_external_domain(
        source_url="https://fr.indeed.com/viewjob?jk=abc123",
        target_url="https://fr.indeed.com/viewjob?jk=abc123",
        application_channel="indeed_easy_apply",
    )


def test_job_target_domain_can_be_persisted_for_future_routing() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        job = Job(
            title="Backend Engineer",
            company="Acme",
            source_url="https://fr.indeed.com/viewjob?jk=abc123",
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        JobRepository(session).update(
            job.id,
            application_target_url="https://jobs.lever.co/acme/backend",
            application_target_domain="jobs.lever.co",
        )
        stored = JobRepository(session).get(job.id)
        stats = AtsDomainStatRepository(session).list_top(limit=5)

    assert stored is not None
    assert stored.application_target_domain == "jobs.lever.co"
    assert stats == []
