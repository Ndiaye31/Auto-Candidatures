from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(slots=True)
class SiteConnector:
    key: str
    label: str
    domains: tuple[str, ...]
    apply_selectors: tuple[str, ...]


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
)

INDEED_CONNECTOR = SiteConnector(
    key="indeed",
    label="Indeed",
    domains=("indeed.com", "fr.indeed.com"),
    apply_selectors=(
        "#indeedApplyButton",
        "button[data-testid='indeedApplyButton']",
        "button:has-text('Postuler maintenant')",
        "button:has-text('Candidature simplifiée')",
        "button:has-text('Apply now')",
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
