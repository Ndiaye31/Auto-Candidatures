from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import json
import re
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models.tables import Job
from app.services.profile_loader import load_profile_payload

TEMPLATES_ROOT = Path(__file__).resolve().parents[1] / "templates"
PLACEHOLDER = "[A COMPLETER]"
MIN_COVER_LETTER_LENGTH = 1200
MAX_COVER_LETTER_LENGTH = 1800


@dataclass(slots=True)
class ApplicationPackResult:
    output_dir: Path
    cover_letter_path: Path
    cv_variant_path: Path
    answers_path: Path
    fields_path: Path


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_ROOT)),
        autoescape=select_autoescape(enabled_extensions=("html", "xml")),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _ensure_sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return cleaned
    if cleaned[-1] not in ".!?":
        return f"{cleaned}."
    return cleaned


def _value_or_placeholder(value: Any) -> str:
    cleaned = _clean_text(value)
    return cleaned if cleaned is not None else PLACEHOLDER


def _stringify_list(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return PLACEHOLDER
    items = [str(item).strip() for item in values if str(item).strip()]
    return ", ".join(items) if items else PLACEHOLDER


def _build_canonical_answers(job: Job, profile: dict[str, Any]) -> dict[str, str]:
    identity = profile.get("identity", {}) if isinstance(profile.get("identity"), dict) else {}
    experience = (
        profile.get("experience", {}) if isinstance(profile.get("experience"), dict) else {}
    )
    preferences = (
        profile.get("preferences", {}) if isinstance(profile.get("preferences"), dict) else {}
    )

    return {
        "candidate.full_name": _value_or_placeholder(identity.get("full_name")),
        "candidate.email": _value_or_placeholder(identity.get("email")),
        "candidate.phone": _value_or_placeholder(identity.get("phone")),
        "candidate.location": _value_or_placeholder(identity.get("location")),
        "candidate.summary": _value_or_placeholder(profile.get("summary")),
        "candidate.current_title": _value_or_placeholder(experience.get("current_title")),
        "candidate.years_experience": _value_or_placeholder(
            experience.get("years_experience")
        ),
        "candidate.top_skills": _stringify_list(profile.get("skills")),
        "candidate.achievements": _stringify_list(profile.get("achievements")),
        "candidate.target_stack": _stringify_list(profile.get("target_stack")),
        "candidate.remote_preference": _value_or_placeholder(preferences.get("remote")),
        "candidate.seniority_target": _value_or_placeholder(preferences.get("seniority")),
        "job.title": _value_or_placeholder(job.title),
        "job.company": _value_or_placeholder(job.company),
        "job.location": _value_or_placeholder(job.location),
        "job.url": _value_or_placeholder(job.source_url),
        "job.source": _value_or_placeholder(job.source),
        "job.description": _value_or_placeholder(job.description),
    }


def _build_cover_letter_paragraphs(answers: dict[str, str]) -> list[str]:
    paragraphs = [
        (
            "Madame, Monsieur,\n"
            f"Je vous adresse ma candidature pour le poste de {answers['job.title']} chez "
            f"{answers['job.company']}. Basé(e) à {answers['candidate.location']}, je m'intéresse "
            f"à cette opportunité située à {answers['job.location']} et identifiée via {answers['job.source']}. "
            f"Mon objectif est de rejoindre un contexte en phase avec ma trajectoire de "
            f"{answers['candidate.current_title']} et avec ma cible de séniorité "
            f"{answers['candidate.seniority_target']}. Je peux partager immédiatement les éléments "
            "complémentaires nécessaires si certains points du poste ou de mon parcours doivent être précisés."
        ),
        (
            f"Mon profil s'appuie sur {answers['candidate.years_experience']} ans d'expérience et sur le "
            f"résumé suivant: {answers['candidate.summary']} Mes compétences principales couvrent "
            f"{answers['candidate.top_skills']}, avec une attention particulière pour la stack cible "
            f"{answers['candidate.target_stack']}. Parmi les éléments concrets que je peux mettre en avant, "
            f"je retiens notamment: {answers['candidate.achievements']}. Je préfère rester factuel(le): "
            "si une technologie, une responsabilité ou un niveau d'exposition n'apparaît pas explicitement "
            "dans ces éléments, je le compléterai avec précision lors d'un échange."
        ),
        (
            f"Le poste mentionne le contexte suivant: {answers['job.description']} Cette description entre en "
            "résonance avec mon intérêt pour des missions claires, utiles au produit et alignées avec mes "
            f"préférences de travail, notamment sur le mode {answers['candidate.remote_preference']}. "
            "Je suis disponible pour détailler les points opérationnels, confirmer les informations encore "
            f"incomplètes et fournir tout complément utile concernant le poste {answers['job.title']}. "
            "Je vous remercie pour votre attention et reste à votre disposition pour la suite du processus."
        ),
    ]
    return [_ensure_sentence(paragraph.replace("\n", " ").strip()) for paragraph in paragraphs]


def _fit_cover_letter_length(paragraphs: list[str]) -> str:
    extras = [
        " Je veille a adapter chaque candidature aux informations verifiees disponibles, sans extrapoler au-dela des faits confirmes.",
        " Lorsque certaines donnees manquent encore, je les signale explicitement afin de les completer proprement avant tout envoi definitif.",
        " Cette approche me permet de garder un dossier coherent, exploitable dans un ATS et simple a reprendre pour un recruteur ou un manager.",
    ]
    working = paragraphs[:]
    idx = 0
    text = "\n\n".join(working)
    while len(text) < MIN_COVER_LETTER_LENGTH and idx < len(extras):
        working[idx % 3] = f"{working[idx % 3]}{extras[idx]}"
        text = "\n\n".join(working)
        idx += 1
    if len(text) > MAX_COVER_LETTER_LENGTH:
        text = text[:MAX_COVER_LETTER_LENGTH].rstrip()
        last_punctuation = max(text.rfind("."), text.rfind("!"), text.rfind("?"))
        if last_punctuation > 0:
            text = text[: last_punctuation + 1]
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    return "\n\n".join(paragraphs[:3])


def _render_template(template_name: str, context: dict[str, Any]) -> str:
    template = _jinja_env().get_template(template_name)
    return template.render(**context).strip() + "\n"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "job"


def generate_application_pack(
    job: Job,
    profile_path: str | Path | None,
    output_root: str | Path,
    *,
    profile_yaml: str | None = None,
    profile_data: dict[str, Any] | None = None,
) -> ApplicationPackResult:
    profile = load_profile_payload(
        profile_path=profile_path,
        profile_yaml=profile_yaml,
        profile_data=profile_data,
    )
    answers = _build_canonical_answers(job, profile)
    cover_letter = _render_template(
        "lm/base.md.jinja",
        {"paragraphs": _build_cover_letter_paragraphs(answers)},
    )
    cover_letter = _fit_cover_letter_length(
        [part.strip() for part in cover_letter.strip().split("\n\n") if part.strip()]
    )

    context = {
        "answers": answers,
        "profile": profile,
        "job": job,
    }
    cv_variant = _render_template("cv/base.md.jinja", context)

    output_dir = Path(output_root) / f"{job.id or 'job'}-{_slugify(job.company)}-{_slugify(job.title)}"
    output_dir.mkdir(parents=True, exist_ok=True)

    cover_letter_path = output_dir / "cover_letter.txt"
    cv_variant_path = output_dir / "cv_variant.md"
    answers_path = output_dir / "answers.json"
    fields_path = output_dir / "fields.csv"

    cover_letter_path.write_text(cover_letter, encoding="utf-8")
    cv_variant_path.write_text(cv_variant, encoding="utf-8")
    answers_path.write_text(
        json.dumps(answers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with fields_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["key", "value"])
        for key, value in answers.items():
            writer.writerow([key, value])

    return ApplicationPackResult(
        output_dir=output_dir,
        cover_letter_path=cover_letter_path,
        cv_variant_path=cv_variant_path,
        answers_path=answers_path,
        fields_path=fields_path,
    )
