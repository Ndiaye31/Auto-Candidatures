from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.models.db import get_session, init_db
from app.services.import_offres import InvalidJobRowError, add_job, import_jobs_from_csv_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app")
    subparsers = parser.add_subparsers(dest="command")

    ingest_parser = subparsers.add_parser("ingest")
    ingest_subparsers = ingest_parser.add_subparsers(dest="ingest_command")

    csv_parser = ingest_subparsers.add_parser("csv")
    csv_parser.add_argument("csv_path")

    add_parser = ingest_subparsers.add_parser("add")
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--company", required=True)
    add_parser.add_argument("--location")
    add_parser.add_argument("--url")
    add_parser.add_argument("--description")
    add_parser.add_argument("--source")

    return parser


def _run_streamlit() -> None:
    from streamlit.web import cli as stcli

    script_path = Path(__file__).resolve().parents[1] / "app" / "main.py"
    sys.argv = ["streamlit", "run", str(script_path), *sys.argv[1:]]
    raise SystemExit(stcli.main())


def _run_ingest_csv(csv_path: str) -> None:
    init_db()
    with get_session() as session:
        result = import_jobs_from_csv_path(session, csv_path)
    print(f"Import terminé: {result.created} créées, {result.skipped} ignorées.")


def _run_ingest_add(args: argparse.Namespace) -> None:
    init_db()
    with get_session() as session:
        _, created = add_job(
            session,
            title=args.title,
            company=args.company,
            location=args.location,
            url=args.url,
            description=args.description,
            source=args.source,
        )
    if created:
        print("Offre ajoutée.")
    else:
        print("Offre déjà présente, aucune nouvelle ligne créée.")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        if args.command == "ingest" and args.ingest_command == "csv":
            _run_ingest_csv(args.csv_path)
            return
        if args.command == "ingest" and args.ingest_command == "add":
            _run_ingest_add(args)
            return
        _run_streamlit()
    except InvalidJobRowError as exc:
        raise SystemExit(str(exc))
