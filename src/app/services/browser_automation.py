from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.services.extraction_dom import FieldCandidate, map_form_fields
from app.services.profile_loader import load_profile_payload
from app.utils.logging import get_logger

LOGGER = get_logger("browser_automation")


@dataclass(slots=True)
class NavigationTarget:
    selector: str
    label: str
    action: str


@dataclass(slots=True)
class StepSnapshot:
    step_index: int
    url: str
    detected_fields: list[FieldCandidate]
    next_target: NavigationTarget | None
    submit_target: NavigationTarget | None
    html: str


@dataclass(slots=True)
class FillAction:
    selector: str
    value: str
    canonical_key: str | None
    confidence: float


@dataclass(slots=True)
class StepExecution:
    snapshot: StepSnapshot
    filled_fields: list[FillAction] = field(default_factory=list)
    clicked_next: bool = False
    stopped_before_submit: bool = False


@dataclass(slots=True)
class AutomationRun:
    steps: list[StepExecution]
    completed: bool
    stop_reason: str


class BrowserStepAdapter(Protocol):
    def current_url(self) -> str: ...

    def page_html(self) -> str: ...

    def fill(self, selector: str, value: str) -> None: ...

    def click(self, selector: str) -> None: ...


def _contains_any(value: str, tokens: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in tokens)


def _extract_navigation_targets(html: str) -> tuple[NavigationTarget | None, NavigationTarget | None]:
    import re

    next_target = None
    submit_target = None
    next_tokens = ("next", "suivant", "continue", "continuer", "étape suivante", "etape suivante")
    submit_tokens = ("submit", "envoyer", "postuler", "apply", "candidater", "terminer", "valider")

    button_pattern = re.compile(
        r"<(?P<tag>button|a)\b(?P<attrs>[^>]*)>(?P<text>.*?)</(?:button|a)>",
        re.IGNORECASE | re.DOTALL,
    )
    input_pattern = re.compile(r"<input\b(?P<attrs>[^>]*)/?>", re.IGNORECASE | re.DOTALL)

    for match in button_pattern.finditer(html):
        attrs = match.group("attrs") or ""
        text = (match.group("text") or "") + " " + attrs
        compact = " ".join(text.split())
        selector = _selector_from_attrs(attrs)
        if not selector:
            continue
        if submit_target is None and _contains_any(compact, submit_tokens):
            submit_target = NavigationTarget(selector=selector, label=compact[:120], action="submit")
        if next_target is None and _contains_any(compact, next_tokens):
            next_target = NavigationTarget(selector=selector, label=compact[:120], action="next")

    for match in input_pattern.finditer(html):
        attrs = match.group("attrs") or ""
        type_match = re.search(r'\btype=["\']?([^"\'>\s]+)', attrs, re.IGNORECASE)
        input_type = (type_match.group(1).lower() if type_match else "text").strip()
        if input_type not in {"submit", "button"}:
            continue
        value_match = re.search(r'\bvalue=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        text = ((value_match.group(1) if value_match else "") + " " + attrs).strip()
        compact = " ".join(text.split())
        selector = _selector_from_attrs(attrs)
        if not selector:
            continue
        if submit_target is None and _contains_any(compact, submit_tokens):
            submit_target = NavigationTarget(selector=selector, label=compact[:120], action="submit")
        if next_target is None and _contains_any(compact, next_tokens):
            next_target = NavigationTarget(selector=selector, label=compact[:120], action="next")
    return next_target, submit_target


def _selector_from_attrs(attrs: str) -> str | None:
    import re

    id_match = re.search(r'\bid=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
    if id_match:
        return f"#{id_match.group(1)}"
    name_match = re.search(r'\bname=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
    if name_match:
        return f'[name="{name_match.group(1)}"]'
    return None


def _build_fill_actions(
    detected_fields: list[FieldCandidate],
    *,
    min_confidence: float,
) -> list[FillAction]:
    actions: list[FillAction] = []
    for candidate in detected_fields:
        if candidate.proposed_value is None:
            continue
        if candidate.confidence < min_confidence:
            continue
        actions.append(
            FillAction(
                selector=candidate.selector,
                value=candidate.proposed_value,
                canonical_key=candidate.canonical_key,
                confidence=candidate.confidence,
            )
        )
    return actions


def capture_step_snapshot(
    adapter: BrowserStepAdapter,
    *,
    profile_path: str | Path | None = None,
    profile_yaml: str | None = None,
    profile_data: dict | None = None,
    step_index: int,
) -> StepSnapshot:
    html = adapter.page_html()
    detected_fields = map_form_fields(
        html,
        profile_path=profile_path,
        profile_yaml=profile_yaml,
        profile_data=profile_data,
    )
    next_target, submit_target = _extract_navigation_targets(html)
    return StepSnapshot(
        step_index=step_index,
        url=adapter.current_url(),
        detected_fields=detected_fields,
        next_target=next_target,
        submit_target=submit_target,
        html=html,
    )


def run_multi_step_assisted_flow(
    adapter: BrowserStepAdapter,
    *,
    profile_path: str | Path | None = None,
    profile_yaml: str | None = None,
    profile_data: dict | None = None,
    max_steps: int = 10,
    min_confidence: float = 0.35,
) -> AutomationRun:
    loaded_profile = load_profile_payload(
        profile_path=profile_path,
        profile_yaml=profile_yaml,
        profile_data=profile_data,
    )

    steps: list[StepExecution] = []
    for step_index in range(max_steps):
        snapshot = capture_step_snapshot(
            adapter,
            profile_data=loaded_profile,
            step_index=step_index,
        )
        fill_actions = _build_fill_actions(
            snapshot.detected_fields,
            min_confidence=min_confidence,
        )
        for action in fill_actions:
            adapter.fill(action.selector, action.value)

        execution = StepExecution(snapshot=snapshot, filled_fields=fill_actions)
        if snapshot.submit_target is not None:
            execution.stopped_before_submit = True
            steps.append(execution)
            LOGGER.info(
                "Automation stopped before submit",
                extra={"step_index": step_index, "url": snapshot.url},
            )
            return AutomationRun(
                steps=steps,
                completed=False,
                stop_reason="submit_detected",
            )

        if snapshot.next_target is None:
            steps.append(execution)
            return AutomationRun(
                steps=steps,
                completed=False,
                stop_reason="next_not_found",
            )

        adapter.click(snapshot.next_target.selector)
        execution.clicked_next = True
        steps.append(execution)

    return AutomationRun(
        steps=steps,
        completed=False,
        stop_reason="max_steps_reached",
    )
