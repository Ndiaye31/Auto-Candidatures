from __future__ import annotations

from app.browser.connectors import (
    GENERIC_CONNECTOR,
    HELLOWORK_CONNECTOR,
    INDEED_CONNECTOR,
    detect_connector,
)


def test_detect_connector_matches_indeed_domain() -> None:
    connector = detect_connector("https://fr.indeed.com/viewjob?jk=abc123")

    assert connector == INDEED_CONNECTOR


def test_detect_connector_matches_hellowork_domain() -> None:
    connector = detect_connector("https://www.hellowork.com/fr-fr/emplois/123.html")

    assert connector == HELLOWORK_CONNECTOR


def test_detect_connector_falls_back_to_generic() -> None:
    connector = detect_connector("https://company-ats.example/apply/123")

    assert connector == GENERIC_CONNECTOR
