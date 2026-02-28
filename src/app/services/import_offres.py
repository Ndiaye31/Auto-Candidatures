from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from urllib.parse import urlparse

from sqlmodel import Session

from app.models.repositories import JobRepository
from app.models.tables import Job

CSV_COLUMNS = ("title", "company", "location", "url", "description", "source")


class InvalidJobRowError(ValueError):
    pass


@dataclass(slots=True)
class ImportResult:
    created: int = 0
    skipped: int = 0


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


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
        "location": _clean_text(payload.get("location")),
        "source_url": _normalize_url(payload.get("url")),
        "description": _clean_text(payload.get("description")),
        "source": _clean_text(payload.get("source")),
    }


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
