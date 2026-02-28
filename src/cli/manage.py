from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.models.db import get_session, init_db
from app.services.auth import AuthError, create_profile, register_user
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

    users_parser = subparsers.add_parser("users")
    users_subparsers = users_parser.add_subparsers(dest="users_command")

    create_user_parser = users_subparsers.add_parser("create")
    create_user_parser.add_argument("--email", required=True)
    create_user_parser.add_argument("--password", required=True)
    create_user_parser.add_argument("--full-name", required=True)

    profiles_parser = subparsers.add_parser("profiles")
    profiles_subparsers = profiles_parser.add_subparsers(dest="profiles_command")

    create_profile_parser = profiles_subparsers.add_parser("create")
    create_profile_parser.add_argument("--user-id", required=True, type=int)
    create_profile_parser.add_argument("--name", required=True)
    create_profile_parser.add_argument("--yaml-path", required=True)
    create_profile_parser.add_argument("--default", action="store_true")

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


def _run_create_user(args: argparse.Namespace) -> None:
    init_db()
    with get_session() as session:
        user = register_user(
            session,
            email=args.email,
            password=args.password,
            full_name=args.full_name,
        )
    print(f"Utilisateur cree: {user.id} {user.email}")


def _run_create_profile(args: argparse.Namespace) -> None:
    init_db()
    profile_yaml = Path(args.yaml_path).read_text(encoding="utf-8")
    with get_session() as session:
        profile = create_profile(
            session,
            user_id=args.user_id,
            name=args.name,
            profile_yaml=profile_yaml,
            is_default=args.default,
        )
    print(f"Profil cree: {profile.id} {profile.name}")


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
        if args.command == "users" and args.users_command == "create":
            _run_create_user(args)
            return
        if args.command == "profiles" and args.profiles_command == "create":
            _run_create_profile(args)
            return
        _run_streamlit()
    except (AuthError, InvalidJobRowError) as exc:
        raise SystemExit(str(exc))
