from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import re
from typing import TextIO
from urllib.parse import urlparse

import pandas as pd
from sqlmodel import Session

from app.models.repositories import CandidateProfileRepository, JobRepository
from app.models.tables import ApplicationStage, Job
from app.services.ats import (
    add_application_event,
    ensure_application,
    update_application_stage,
)

CSV_COLUMNS = ("title", "company", "location", "url", "description", "source")
EXCEL_ALERT_COLUMNS = (
    "ID (jk)",
    "Titre du poste",
    "URL de l'offre",
    "Description",
    "Source",
    "Date email",
    "Sujet email",
    "Expéditeur",
    "Statut",
    "Type Candidature",
    "Notes",
)


class InvalidJobRowError(ValueError):
    pass


@dataclass(slots=True)
class ImportResult:
    created: int = 0
    skipped: int = 0


def _coerce_cell(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _compact_spaces(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    return " ".join(cleaned.split())


def _normalize_url(url: str | None) -> str | None:
    cleaned = _clean_text(url)
    if cleaned is None:
        return None

    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise InvalidJobRowError(f"Invalid URL: {cleaned}")

    normalized_path = parsed.path.rstrip("/") or ""
    return parsed._replace(path=normalized_path, fragment="").geturl()


def normalize_job_payload(payload: dict[str, str | None]) -> dict[str, str | None]:
    title = _clean_text(payload.get("title"))
    company = _clean_text(payload.get("company"))
    if not title or not company:
        raise InvalidJobRowError("Both title and company are required")

    return {
        "title": title,
        "company": company,
        "location": _compact_spaces(payload.get("location")),
        "source_url": _normalize_url(payload.get("url")),
        "description": _compact_spaces(payload.get("description")),
        "source": _compact_spaces(payload.get("source")),
    }


def _strip_after_markers(value: str) -> str:
    markers = [
        " Candidature simplifiee",
        " Candidature simplifiée",
        " Dans le cadre",
        " Nous recherchons",
        " Employeur reactif",
        " Employeur réactif",
        " il y a ",
        " Publié",
        " Publie",
    ]
    current = value
    for marker in markers:
        position = current.find(marker)
        if position != -1:
            current = current[:position]
    return current.strip()


def _parse_title_company_location(
    raw_title: str | None,
    raw_description: str | None,
) -> tuple[str | None, str | None, str | None]:
    title_source = _compact_spaces(raw_title)
    description_source = _compact_spaces(raw_description)
    source = title_source or description_source
    if source is None:
        return None, None, None

    cleaned = _strip_after_markers(source)
    location_match = re.search(r"([A-Z][A-Za-zÀ-ÿ'’ -]+ \(\d{2}\))", cleaned)
    location = location_match.group(1) if location_match else None
    if location:
        left = cleaned[: location_match.start()].strip()
    else:
        left = cleaned

    rating_match = re.search(r"\s\d+(?:[.,]\d+)?\s", left)
    company = None
    title = left
    company_markers = {"h/f", "f/h", "h/f/nb", "f/h/nb", "nb"}
    if rating_match:
        before_rating = left[: rating_match.start()].strip()
        after_rating = left[rating_match.start() :].strip()
        tokens = before_rating.split()
        split_index = None
        for idx in range(1, len(tokens)):
            previous = tokens[idx - 1].lower().strip(",")
            current = tokens[idx]
            if previous in company_markers and current[:1].isupper():
                split_index = idx
                break
        if split_index is not None:
            title = " ".join(tokens[:split_index]).strip()
            company = " ".join(tokens[split_index:]).strip()
        else:
            title = before_rating
        if company is None:
            company = after_rating.split()[0] if after_rating else None
    else:
        tokens = left.split()
        split_index = None
        for idx in range(1, len(tokens)):
            previous = tokens[idx - 1].lower().strip(",")
            current = tokens[idx]
            if previous in company_markers and current[:1].isupper():
                split_index = idx
                break
        if split_index is not None:
            title = " ".join(tokens[:split_index]).strip()
            company = " ".join(tokens[split_index:]).strip()

    title = _compact_spaces(title)
    company = _compact_spaces(company)
    if company is not None:
        company = re.sub(r"\s+\d+(?:[.,]\d+)?$", "", company).strip() or None
    if company is None and description_source:
        company = "Entreprise non extraite"
    return title, company, location


def _normalize_application_channel(source: str | None, candidacy_type: str | None) -> str | None:
    combined = " ".join(filter(None, [_compact_spaces(source), _compact_spaces(candidacy_type)])).lower()
    if not combined:
        return None
    if "indeed" in combined and "easy" in combined:
        return "indeed_easy_apply"
    if "indeed" in combined:
        return "indeed_external"
    if "hellowork" in combined and "easy" in combined:
        return "hellowork_easy_apply"
    if "hellowork" in combined:
        return "hellowork_external"
    if "easy" in combined:
        return "easy_apply"
    return "external_ats"


def _map_stage_from_status(status: str | None) -> ApplicationStage:
    normalized = (_compact_spaces(status) or "").lower()
    if normalized in {"envoyee", "envoyé", "applied", "submitted", "envoye"}:
        return ApplicationStage.APPLIED
    if normalized in {"refusee", "refusée", "rejected", "refusee"}:
        return ApplicationStage.REJECTED
    if normalized in {"entretien", "screening", "interview"}:
        return ApplicationStage.SCREENING
    if normalized in {"offre", "offer"}:
        return ApplicationStage.OFFER
    if normalized in {"pack pret", "pack prêt", "pack_ready"}:
        return ApplicationStage.PACK_READY
    if normalized in {"a relancer", "to_review", "a revoir"}:
        return ApplicationStage.TO_REVIEW
    return ApplicationStage.SOURCED


def _ingest_alert_row(
    session: Session,
    row: dict[str, object],
    *,
    profile_id: int | None,
) -> bool:
    title, company, location = _parse_title_company_location(
        _coerce_cell(row.get("Titre du poste")),
        _coerce_cell(row.get("Description")),
    )
    if not title:
        raise InvalidJobRowError("Unable to extract a job title from alert row")
    if not company:
        company = "Entreprise non extraite"

    job, created = add_job(
        session,
        title=title,
        company=company,
        location=location,
        url=_coerce_cell(row.get("URL de l'offre")),
        description=_coerce_cell(row.get("Description")),
        source=_coerce_cell(row.get("Source")),
    )

    if profile_id is not None:
        application_channel = _normalize_application_channel(
            _coerce_cell(row.get("Source")),
            _coerce_cell(row.get("Type Candidature")),
        )
        application = ensure_application(
            session,
            job_id=job.id,
            profile_id=profile_id,
            application_channel=application_channel,
        )
        stage = _map_stage_from_status(_coerce_cell(row.get("Statut")))
        update_application_stage(
            session,
            application_id=application.id,
            stage=stage,
            note="Import depuis fichier d'alertes job_offers",
            outcome_reason=_coerce_cell(row.get("Notes")),
        )
        add_application_event(
            session,
            application_id=application.id,
            event_type="alert_import",
            note=_coerce_cell(row.get("Notes")) or "Import depuis fichier d'alertes",
            payload={
                "external_id": _coerce_cell(row.get("ID (jk)")),
                "email_date": _coerce_cell(row.get("Date email")),
                "email_subject": _coerce_cell(row.get("Sujet email")),
                "sender": _coerce_cell(row.get("Expéditeur")),
                "candidacy_type": _coerce_cell(row.get("Type Candidature")),
            },
        )

    return created


def add_job(
    session: Session,
    *,
    title: str,
    company: str,
    location: str | None = None,
    url: str | None = None,
    description: str | None = None,
    source: str | None = None,
) -> tuple[Job, bool]:
    payload = normalize_job_payload(
        {
            "title": title,
            "company": company,
            "location": location,
            "url": url,
            "description": description,
            "source": source,
        }
    )
    repository = JobRepository(session)

    source_url = payload["source_url"]
    if source_url:
        existing = repository.get_by_source_url(source_url)
        if existing is not None:
            return existing, False

    job = Job(**payload)
    return repository.create(job), True


def import_jobs_from_csv(session: Session, csv_file: TextIO) -> ImportResult:
    reader = csv.DictReader(csv_file)
    missing_columns = [column for column in CSV_COLUMNS if column not in reader.fieldnames]
    if missing_columns:
        raise InvalidJobRowError(
            f"Missing CSV columns: {', '.join(sorted(missing_columns))}"
        )

    result = ImportResult()
    for row in reader:
        _, created = add_job(
            session,
            title=row.get("title"),
            company=row.get("company"),
            location=row.get("location"),
            url=row.get("url"),
            description=row.get("description"),
            source=row.get("source"),
        )
        if created:
            result.created += 1
        else:
            result.skipped += 1
    return result


def import_jobs_from_csv_path(session: Session, csv_path: str | Path) -> ImportResult:
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        return import_jobs_from_csv(session, handle)


def import_jobs_from_alerts_excel_path(
    session: Session,
    excel_path: str | Path,
    *,
    profile_id: int | None = None,
) -> ImportResult:
    dataframe = pd.read_excel(Path(excel_path))
    missing_columns = [
        column for column in EXCEL_ALERT_COLUMNS if column not in dataframe.columns
    ]
    if missing_columns:
        raise InvalidJobRowError(
            f"Missing Excel columns: {', '.join(sorted(missing_columns))}"
        )

    effective_profile_id = profile_id
    if effective_profile_id is None:
        default_profile = CandidateProfileRepository(session).get_default()
        effective_profile_id = default_profile.id if default_profile else None

    result = ImportResult()
    for row in dataframe.to_dict(orient="records"):
        created = _ingest_alert_row(
            session,
            row,
            profile_id=effective_profile_id,
        )
        if created:
            result.created += 1
        else:
            result.skipped += 1
    return result
