from __future__ import annotations

from pathlib import Path

from app.services.extraction_dom import map_form_fields


def test_map_form_fields_matches_basic_contact_fields() -> None:
    html = Path("tests/fixtures/form_basic.html").read_text(encoding="utf-8")

    candidates = map_form_fields(html, Path("tests/fixtures/profile_mapping.yaml"))

    assert [candidate.canonical_key for candidate in candidates] == [
        "candidate.email",
        "candidate.phone",
        "candidate.city",
    ]
    assert candidates[0].proposed_value == "claire.martin@example.com"
    assert candidates[1].proposed_value == "0601020304"
    assert candidates[2].proposed_value == "Lyon"
    assert all(candidate.confidence >= 0.4 for candidate in candidates)


def test_map_form_fields_matches_professional_links() -> None:
    html = Path("tests/fixtures/form_professional_links.html").read_text(
        encoding="utf-8"
    )

    candidates = map_form_fields(html, Path("tests/fixtures/profile_mapping.yaml"))

    assert [candidate.canonical_key for candidate in candidates] == [
        "candidate.linkedin_url",
        "candidate.github_url",
    ]
    assert candidates[0].selector == "#linkedin_url"
    assert candidates[1].proposed_value == "https://github.com/clairemartin"
    assert any("aria-label='GitHub profile'" in reason for reason in candidates[1].reasons)


def test_map_form_fields_matches_salary_and_availability() -> None:
    html = Path("tests/fixtures/form_compensation.html").read_text(encoding="utf-8")

    candidates = map_form_fields(html, Path("tests/fixtures/profile_mapping.yaml"))

    assert [candidate.canonical_key for candidate in candidates] == [
        "candidate.salary_expectation",
        "candidate.availability",
    ]
    assert candidates[0].proposed_value == "55000"
    assert candidates[1].proposed_value == "2026-04-01"
    assert any("label='Disponibilité'" in reason for reason in candidates[1].reasons)
