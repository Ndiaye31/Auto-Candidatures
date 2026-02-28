from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(slots=True)
class SiteConnector:
    key: str
    label: str
    domains: tuple[str, ...]
    apply_selectors: tuple[str, ...]
    apply_texts: tuple[str, ...]


GENERIC_CONNECTOR = SiteConnector(
    key="generic",
    label="Generic multi-step",
    domains=(),
    apply_selectors=(
        "a[data-testid='apply-button']",
        "button[data-testid='apply-button']",
        "a[href*='apply']",
        "button:has-text('Postuler')",
        "button:has-text('Apply')",
    ),
    apply_texts=("Postuler", "Apply", "Candidater"),
)

INDEED_CONNECTOR = SiteConnector(
    key="indeed",
    label="Indeed",
    domains=("indeed.com", "fr.indeed.com"),
    apply_selectors=(
        "#indeedApplyButton",
        "button[data-testid='indeedApplyButton']",
        "a[data-testid='indeedApplyButton']",
        "button[data-testid='apply-button']",
        "a[data-testid='apply-button']",
        "button[aria-label*='Postuler']",
        "a[aria-label*='Postuler']",
        "button:has-text('Postuler maintenant')",
        "button:has-text('Candidature simplifiée')",
        "button:has-text('Postuler')",
        "a:has-text('Postuler')",
        "button:has-text('Apply now')",
        "a:has-text('Apply now')",
    ),
    apply_texts=(
        "Postuler maintenant",
        "Candidature simplifiée",
        "Postuler",
        "Apply now",
        "Apply",
    ),
)

HELLOWORK_CONNECTOR = SiteConnector(
    key="hellowork",
    label="HelloWork",
    domains=("hellowork.com", "www.hellowork.com"),
    apply_selectors=(
        "a[data-cy='apply-button']",
        "button[data-cy='apply-button']",
        "button:has-text('Postuler')",
        "a:has-text('Postuler')",
        "button:has-text('Candidater')",
    ),
    apply_texts=("Postuler", "Candidater", "Je postule"),
)

SUPPORTED_CONNECTORS = (
    INDEED_CONNECTOR,
    HELLOWORK_CONNECTOR,
)


def detect_connector(url: str | None) -> SiteConnector:
    if not url:
        return GENERIC_CONNECTOR
    hostname = urlparse(url).netloc.lower()
    for connector in SUPPORTED_CONNECTORS:
        if any(hostname.endswith(domain) for domain in connector.domains):
            return connector
    return GENERIC_CONNECTOR


def resolve_connector(
    *,
    url: str | None,
    application_channel: str | None = None,
) -> SiteConnector:
    normalized_channel = (application_channel or "").strip().lower()
    if normalized_channel == "indeed_easy_apply":
        return INDEED_CONNECTOR
    if normalized_channel == "hellowork_easy_apply":
        return HELLOWORK_CONNECTOR
    if normalized_channel.endswith("_external") or normalized_channel == "external_ats":
        return GENERIC_CONNECTOR
    return detect_connector(url)


def describe_application_channel(application_channel: str | None) -> str:
    normalized_channel = (application_channel or "").strip().lower()
    if normalized_channel == "indeed_easy_apply":
        return "Indeed Easy Apply"
    if normalized_channel == "indeed_external":
        return "Indeed External ATS"
    if normalized_channel == "hellowork_easy_apply":
        return "HelloWork Easy Apply"
    if normalized_channel == "hellowork_external":
        return "HelloWork External ATS"
    if normalized_channel == "easy_apply":
        return "Easy Apply"
    if normalized_channel == "external_ats":
        return "External ATS"
    return "Canal non determine"
