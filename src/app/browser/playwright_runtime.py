from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def run_playwright_multi_step_flow(
    *,
    start_url: str,
    profile_path: str | Path | None = None,
    profile_yaml: str | None = None,
    profile_data: dict | None = None,
    config: PlaywrightSessionConfig | None = None,
):
    runtime_config = config or PlaywrightSessionConfig()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=runtime_config.headless,
            slow_mo=runtime_config.slow_mo_ms,
        )
        page = browser.new_page()
        page.goto(start_url, wait_until="domcontentloaded")
        result = run_multi_step_assisted_flow(
            SyncPlaywrightAdapter(page),
            profile_path=profile_path,
            profile_yaml=profile_yaml,
            profile_data=profile_data,
        )
        browser.close()
        return result
