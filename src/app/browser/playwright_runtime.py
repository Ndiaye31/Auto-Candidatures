from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


@dataclass(slots=True)
class PlaywrightFlowResult:
    connector: str
    apply_click_selector: str | None
    automation_run: Any


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
            clicked_apply_selector = _safe_click_first_available(
                page,
                selected_connector.apply_selectors,
            )
        result = run_multi_step_assisted_flow(
            SyncPlaywrightAdapter(page),
            profile_path=profile_path,
            profile_yaml=profile_yaml,
            profile_data=profile_data,
        )
        browser.close()
        return PlaywrightFlowResult(
            connector=selected_connector.key,
            apply_click_selector=clicked_apply_selector,
            automation_run=result,
        )
