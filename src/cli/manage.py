from __future__ import annotations

from pathlib import Path
import sys


def main() -> None:
    from streamlit.web import cli as stcli

    script_path = Path(__file__).resolve().parents[1] / "app" / "main.py"
    sys.argv = ["streamlit", "run", str(script_path), *sys.argv[1:]]
    raise SystemExit(stcli.main())
