from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.browser.connectors import GENERIC_CONNECTOR, SiteConnector, detect_connector
from app.services.browser_automation import BrowserStepAdapter, run_multi_step_assisted_flow


@dataclass(slots=True)
class PlaywrightSessionConfig:
    headless: bool = False
    slow_mo_ms: int = 0


class SyncPlaywrightAdapter(BrowserStepAdapter):
    def __init__(self, page: Any) -> None:
        self.page = page

    def current_url(self) -> str:
        return str(self.page.url)

    def page_html(self) -> str:
        return self.page.content()

    def fill(self, selector: str, value: str) -> None:
        self.page.locator(selector).first.fill(value)

    def click(self, selector: str) -> None:
        self.page.locator(selector).first.click()


def _configure_windows_event_loop_policy() -> None:
    if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def _safe_click_first_available(page: Any, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() > 0 and locator.is_visible():
                locator.click()
                page.wait_for_load_state("domcontentloaded")
                return selector
        except Exception:
            continue
    return None


def _safe_click_by_text(page: Any, texts: tuple[str, ...]) -> str | None:
    for text in texts:
        try:
            for role in ("button", "link"):
                locator = page.get_by_role(role, name=text, exact=False).first
                if locator.count() > 0 and locator.is_visible():
                    locator.click()
                    page.wait_for_load_state("domcontentloaded")
                    return f"{role}:{text}"
        except Exception:
            continue
    return None


def _try_open_apply_flow(page: Any, connector: SiteConnector) -> str | None:
    scroll_positions = (0, 0.4, 0.8, 1.0)
    for position in scroll_positions:
        try:
            page.evaluate(
                "(position) => window.scrollTo(0, document.body.scrollHeight * position)",
                position,
            )
            page.wait_for_timeout(250)
        except Exception:
            pass
        clicked = _safe_click_first_available(page, connector.apply_selectors)
        if clicked is not None:
            return clicked
        clicked = _safe_click_by_text(page, connector.apply_texts)
        if clicked is not None:
            return clicked
    return None


def _write_snapshot(connector_key: str, html: str) -> Path:
    snapshot_dir = Path("data/browser_snapshots")
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_path = snapshot_dir / f"{connector_key}-{timestamp}.html"
    snapshot_path.write_text(html, encoding="utf-8")
    return snapshot_path


@dataclass(slots=True)
class PlaywrightFlowResult:
    connector: str
    apply_click_selector: str | None
    automation_run: Any
    snapshot_path: Path | None
    resolved_url: str
    resolved_domain: str | None
    resolved_connector: str


def run_playwright_multi_step_flow(
    *,
    start_url: str,
    profile_path: str | Path | None = None,
    profile_yaml: str | None = None,
    profile_data: dict | None = None,
    config: PlaywrightSessionConfig | None = None,
    connector: SiteConnector | None = None,
) -> PlaywrightFlowResult:
    runtime_config = config or PlaywrightSessionConfig()
    selected_connector = connector or detect_connector(start_url)
    from playwright.sync_api import sync_playwright

    _configure_windows_event_loop_policy()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=runtime_config.headless,
            slow_mo=runtime_config.slow_mo_ms,
        )
        page = browser.new_page()
        page.goto(start_url, wait_until="domcontentloaded")
        clicked_apply_selector = None
        if selected_connector is not GENERIC_CONNECTOR:
            clicked_apply_selector = _try_open_apply_flow(page, selected_connector)
        result = run_multi_step_assisted_flow(
            SyncPlaywrightAdapter(page),
            profile_path=profile_path,
            profile_yaml=profile_yaml,
            profile_data=profile_data,
        )
        resolved_url = str(page.url)
        resolved_domain = urlparse(resolved_url).netloc.lower() or None
        if resolved_domain and resolved_domain.startswith("www."):
            resolved_domain = resolved_domain[4:]
        resolved_connector = detect_connector(resolved_url).key
        snapshot_path = None
        if result.steps:
            final_html = result.steps[-1].snapshot.html
            if result.stop_reason in {"next_not_found", "submit_detected"}:
                snapshot_path = _write_snapshot(selected_connector.key, final_html)
        browser.close()
        return PlaywrightFlowResult(
            connector=selected_connector.key,
            apply_click_selector=clicked_apply_selector,
            automation_run=result,
            snapshot_path=snapshot_path,
            resolved_url=resolved_url,
            resolved_domain=resolved_domain,
            resolved_connector=resolved_connector,
        )
