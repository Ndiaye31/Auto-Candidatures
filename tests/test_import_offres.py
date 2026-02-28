from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
from sqlmodel import Session

from app.models.db import create_db_engine, init_db
from app.models.repositories import ApplicationRepository, JobRepository
from app.models.tables import ApplicationStage
from app.services.import_offres import (
    add_job,
    import_jobs_from_alerts_excel_path,
    import_jobs_from_csv,
)
from app.services.profiles import ensure_default_profile


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


def test_import_jobs_from_alerts_excel_maps_and_deduplicates_rows(tmp_path: Path) -> None:
    engine = create_db_engine("sqlite://")
    init_db(engine)
    excel_path = tmp_path / "job_offers.xlsx"
    dataframe = pd.DataFrame(
        [
            {
                "ID (jk)": "abc123",
                "Titre du poste": "Data Analyst H/F NOVEOCARE 2.7 Chartres (28) Candidature simplifiée",
                "URL de l'offre": "https://fr.indeed.com/viewjob?jk=abc123",
                "Description": "Data Analyst H/F Chartres (28) Candidature simplifiée Analyse de données",
                "Source": "Scrapper offres Indeed",
                "Date email": "Tue, 17 Feb 2026 01:06:03 +0000",
                "Sujet email": "Alerte Indeed",
                "Expéditeur": "\"Indeed\" <donotreply@jobalert.indeed.com>",
                "Statut": "envoyee",
                "Type Candidature": "Easy candidature",
                "Notes": "Candidature simplifiée",
            },
            {
                "ID (jk)": "abc123",
                "Titre du poste": "Data Analyst H/F NOVEOCARE 2.7 Chartres (28) Candidature simplifiée",
                "URL de l'offre": "https://fr.indeed.com/viewjob?jk=abc123",
                "Description": "Duplicate row",
                "Source": "Scrapper offres Indeed",
                "Date email": "Tue, 17 Feb 2026 01:06:03 +0000",
                "Sujet email": "Alerte Indeed",
                "Expéditeur": "\"Indeed\" <donotreply@jobalert.indeed.com>",
                "Statut": "envoyee",
                "Type Candidature": "Easy candidature",
                "Notes": "Duplicate",
            },
        ]
    )
    dataframe.to_excel(excel_path, index=False)

    with Session(engine) as session:
        profile = ensure_default_profile(session)
        result = import_jobs_from_alerts_excel_path(session, excel_path, profile_id=profile.id)
        jobs = JobRepository(session).list()
        application = ApplicationRepository(session).get_by_job_and_profile(
            jobs[0].id, profile.id
        )

    assert result.created == 1
    assert result.skipped == 1
    assert len(jobs) == 1
    assert jobs[0].title == "Data Analyst H/F"
    assert jobs[0].company == "NOVEOCARE"
    assert jobs[0].location == "Chartres (28)"
    assert application is not None
    assert application.application_channel == "indeed_easy_apply"
    assert application.stage == ApplicationStage.APPLIED
