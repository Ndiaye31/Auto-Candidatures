from __future__ import annotations

from app.browser.connectors import (
    describe_application_channel,
    GENERIC_CONNECTOR,
    GREENHOUSE_CONNECTOR,
    HELLOWORK_CONNECTOR,
    INDEED_CONNECTOR,
    LEVER_CONNECTOR,
    SMARTRECRUITERS_CONNECTOR,
    WORKDAY_CONNECTOR,
    detect_connector,
    resolve_connector,
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


def test_detect_connector_matches_known_external_ats_domains() -> None:
    assert detect_connector("https://jobs.lever.co/acme/backend") == LEVER_CONNECTOR
    assert (
        detect_connector("https://acme.wd3.myworkdayjobs.com/job/Paris")
        == WORKDAY_CONNECTOR
    )
    assert (
        detect_connector("https://boards.greenhouse.io/acme/jobs/123")
        == GREENHOUSE_CONNECTOR
    )
    assert (
        detect_connector("https://jobs.smartrecruiters.com/Acme/123")
        == SMARTRECRUITERS_CONNECTOR
    )


def test_resolve_connector_prefers_application_channel_over_url() -> None:
    connector = resolve_connector(
        url="https://company-ats.example/apply/123",
        application_channel="indeed_easy_apply",
    )

    assert connector == INDEED_CONNECTOR


def test_resolve_connector_forces_generic_on_external_channel() -> None:
    connector = resolve_connector(
        url="https://fr.indeed.com/viewjob?jk=abc123",
        application_channel="indeed_external",
    )

    assert connector == GENERIC_CONNECTOR


def test_resolve_connector_uses_learned_external_target_domain() -> None:
    connector = resolve_connector(
        url="https://fr.indeed.com/viewjob?jk=abc123",
        application_channel="indeed_external",
        target_domain="jobs.lever.co",
    )

    assert connector == LEVER_CONNECTOR


def test_describe_application_channel_returns_human_label() -> None:
    assert describe_application_channel("hellowork_easy_apply") == "HelloWork Easy Apply"
