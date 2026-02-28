from __future__ import annotations

import csv
import json
from pathlib import Path

from app.models.tables import Job
from app.services.generation_pack import (
    MAX_COVER_LETTER_LENGTH,
    MIN_COVER_LETTER_LENGTH,
    PLACEHOLDER,
    generate_application_pack,
)


def test_generate_application_pack_writes_expected_files(tmp_path: Path) -> None:
    job = Job(
        id=7,
        title="Backend Engineer",
        company="Acme",
        location="Paris",
        source_url="https://example.test/jobs/backend",
        source="LinkedIn",
        description=(
            "Concevoir des API Python et FastAPI, collaborer avec l'equipe produit "
            "et maintenir une plateforme PostgreSQL en mode hybride."
        ),
    )

    result = generate_application_pack(
        job,
        profile_path=Path("tests/fixtures/profile_pack.yaml"),
        output_root=tmp_path,
    )

    assert result.cover_letter_path.exists()
    assert result.cv_variant_path.exists()
    assert result.answers_path.exists()
    assert result.fields_path.exists()

    cover_letter = result.cover_letter_path.read_text(encoding="utf-8").strip()
    paragraphs = [part for part in cover_letter.split("\n\n") if part.strip()]
    assert len(paragraphs) == 3
    assert MIN_COVER_LETTER_LENGTH <= len(cover_letter) <= MAX_COVER_LETTER_LENGTH

    cv_variant = result.cv_variant_path.read_text(encoding="utf-8")
    assert "# Claire Martin" in cv_variant
    assert "Backend Engineer" in cv_variant

    answers = json.loads(result.answers_path.read_text(encoding="utf-8"))
    assert answers["candidate.full_name"] == "Claire Martin"
    assert answers["job.company"] == "Acme"

    with result.fields_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["key", "value"]
    assert ["job.title", "Backend Engineer"] in rows


def test_generate_application_pack_uses_placeholders_for_missing_data(tmp_path: Path) -> None:
    job = Job(
        id=8,
        title="Data Engineer",
        company="Beta",
        description="Construire des pipelines de donnees Python.",
    )

    result = generate_application_pack(
        job,
        profile_path=Path("tests/fixtures/profile_pack_missing.yaml"),
        output_root=tmp_path,
    )

    cover_letter = result.cover_letter_path.read_text(encoding="utf-8")
    assert PLACEHOLDER in cover_letter
    assert len([part for part in cover_letter.strip().split("\n\n") if part.strip()]) == 3

    answers = json.loads(result.answers_path.read_text(encoding="utf-8"))
    assert answers["candidate.email"] == PLACEHOLDER
    assert answers["job.location"] == PLACEHOLDER
