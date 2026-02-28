from __future__ import annotations

from app.main import LAUNCH_INSTRUCTIONS, run


def test_run_returns_streamlit_instructions() -> None:
    try:
        run()
    except SystemExit as exc:
        assert str(exc) == LAUNCH_INSTRUCTIONS
    else:
        raise AssertionError("run() should stop with launch instructions")
