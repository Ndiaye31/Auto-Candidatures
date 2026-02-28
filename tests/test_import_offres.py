from __future__ import annotations

from io import StringIO

from sqlmodel import Session

from app.models.db import create_db_engine, init_db
from app.models.repositories import JobRepository
from app.services.import_offres import add_job, import_jobs_from_csv


def test_import_jobs_from_csv_imports_three_rows_and_skips_duplicate_url() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)
    csv_content = """title,company,location,url,description,source
 Backend Engineer , Acme , Paris , https://example.test/jobs/1/ , Python role , linkedin
Data Engineer,Acme,Remote,https://example.test/jobs/2,Data role,site
Backend Engineer duplicate,Acme,Paris,https://example.test/jobs/1,Duplicate,site
"""

    with Session(engine) as session:
        result = import_jobs_from_csv(session, StringIO(csv_content))
        jobs = JobRepository(session).list()

    assert result.created == 2
    assert result.skipped == 1
    assert len(jobs) == 2
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].company == "Acme"
    assert jobs[0].source_url == "https://example.test/jobs/1"


def test_add_job_normalizes_values_and_persists_source() -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)

    with Session(engine) as session:
        job, created = add_job(
            session,
            title="  Platform Engineer ",
            company=" Acme ",
            location=" Remote ",
            url="https://example.test/jobs/platform/ ",
            description=" Build infra ",
            source=" referral ",
        )

    assert created is True
    assert job.title == "Platform Engineer"
    assert job.company == "Acme"
    assert job.location == "Remote"
    assert job.source_url == "https://example.test/jobs/platform"
    assert job.description == "Build infra"
    assert job.source == "referral"
