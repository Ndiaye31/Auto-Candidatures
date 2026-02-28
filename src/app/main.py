from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.models.db import init_db  # noqa: E402


LAUNCH_INSTRUCTIONS = (
    "Cette application est une interface Streamlit.\n"
    "Lance-la avec l'une de ces commandes:\n"
    "  streamlit run src/app/main.py\n"
    "  python -m streamlit run src/app/main.py\n"
    "  app"
)


def _is_streamlit_runtime() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


def _render_home() -> None:
    import streamlit as st

    init_db()
    st.set_page_config(page_title="Job Application Assistant", layout="wide")
    st.title("Job Application Assistant")
    st.caption("V1 - Import, Scoring, Pack, Postuler (assisté)")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Offres", "0")
    col2.metric("Scorées", "0")
    col3.metric("Packs", "0")
    col4.metric("Pipeline", "0")

    st.divider()
    st.subheader("État")
    st.write(
        f"Horodatage: {datetime.now(timezone.utc).isoformat(timespec='seconds')}"
    )
    st.info("DB initialisée. Prochaines pages: Import, Scoring, Postuler, Pipeline.")


def run() -> None:
    raise SystemExit(LAUNCH_INSTRUCTIONS)


if __name__ == "__main__":
    if not _is_streamlit_runtime():
        raise SystemExit(LAUNCH_INSTRUCTIONS)
    _render_home()
