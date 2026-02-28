from __future__ import annotations

from dataclasses import dataclass

from app.services.browser_automation import (
    BrowserStepAdapter,
    run_multi_step_assisted_flow,
)


@dataclass
class FakePage:
    url: str
    html: str


class FakeAdapter(BrowserStepAdapter):
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages
        self.index = 0
        self.fills: list[tuple[str, str]] = []
        self.clicks: list[str] = []

    def current_url(self) -> str:
        return self.pages[self.index].url

    def page_html(self) -> str:
        return self.pages[self.index].html

    def fill(self, selector: str, value: str) -> None:
        self.fills.append((selector, value))

    def click(self, selector: str) -> None:
        self.clicks.append(selector)
        if self.index < len(self.pages) - 1:
            self.index += 1


PROFILE = {
    "identity": {
        "email": "claire@example.com",
        "phone": "0601020304",
        "city": "Lyon",
    },
    "urls": {
        "linkedin": "https://www.linkedin.com/in/claire",
        "github": "https://github.com/claire",
    },
    "salary": {"expected": "55000"},
    "availability": {"start_date": "2026-04-01"},
}


def test_multi_step_flow_fills_fields_and_stops_before_submit() -> None:
    adapter = FakeAdapter(
        [
            FakePage(
                url="https://example.test/apply/step-1",
                html="""
                <form>
                  <label for="email">Email</label>
                  <input id="email" name="candidate_email" type="email" />
                  <button id="next-step">Suivant</button>
                </form>
                """,
            ),
            FakePage(
                url="https://example.test/apply/step-2",
                html="""
                <form>
                  <label for="phone">Téléphone</label>
                  <input id="phone" name="phone_number" type="tel" />
                  <button id="submit-final">Envoyer ma candidature</button>
                </form>
                """,
            ),
        ]
    )

    result = run_multi_step_assisted_flow(adapter, profile_data=PROFILE)

    assert result.stop_reason == "submit_detected"
    assert result.steps[0].clicked_next is True
    assert result.steps[1].stopped_before_submit is True
    assert ("#email", "claire@example.com") in adapter.fills
    assert ("#phone", "0601020304") in adapter.fills
    assert "#next-step" in adapter.clicks
    assert "#submit-final" not in adapter.clicks


def test_multi_step_flow_stops_when_no_next_is_found() -> None:
    adapter = FakeAdapter(
        [
            FakePage(
                url="https://example.test/apply/start",
                html="""
                <form>
                  <label for="city">Ville</label>
                  <input id="city" name="city" type="text" />
                </form>
                """,
            )
        ]
    )

    result = run_multi_step_assisted_flow(adapter, profile_data=PROFILE)

    assert result.stop_reason == "next_not_found"
    assert ("#city", "Lyon") in adapter.fills
    assert adapter.clicks == []
