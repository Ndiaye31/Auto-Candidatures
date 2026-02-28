from __future__ import annotations

from urllib.parse import urlparse

from sqlmodel import Session

from app.browser.connectors import GENERIC_CONNECTOR, detect_connector
from app.models.repositories import AtsDomainStatRepository
from app.models.tables import AtsDomainStat


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if "://" in normalized:
        normalized = urlparse(normalized).netloc.lower()
    normalized = normalized.split("@")[-1].strip(".")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized or None


def should_record_external_domain(
    *,
    source_url: str | None,
    target_url: str | None,
    application_channel: str | None,
) -> bool:
    normalized_channel = (application_channel or "").strip().lower()
    source_domain = normalize_domain(source_url)
    target_domain = normalize_domain(target_url)
    if target_domain is None:
        return False
    if source_domain is None:
        return normalized_channel.endswith("_external") or normalized_channel == "external_ats"
    if normalized_channel.endswith("_external") or normalized_channel == "external_ats":
        return target_domain != source_domain
    return source_domain is not None and target_domain != source_domain


def record_external_ats_domain(
    session: Session,
    *,
    target_url: str,
) -> AtsDomainStat | None:
    domain = normalize_domain(target_url)
    if domain is None:
        return None

    connector = detect_connector(target_url)
    connector_key = connector.key
    if connector is GENERIC_CONNECTOR:
        connector_key = "generic_external"

    repository = AtsDomainStatRepository(session)
    stat = repository.get_by_domain(domain)
    if stat is None:
        return repository.create(
            AtsDomainStat(
                domain=domain,
                connector_key=connector_key,
                seen_count=1,
                sample_url=target_url,
            )
        )

    return repository.update(
        stat.id,
        connector_key=connector_key,
        seen_count=stat.seen_count + 1,
        sample_url=target_url,
    )


def list_top_external_ats(session: Session, limit: int = 5) -> list[AtsDomainStat]:
    return AtsDomainStatRepository(session).list_top(limit=limit)
