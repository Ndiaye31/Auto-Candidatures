# Job Application Assistant

Application locale pour centraliser des offres, les scorer, generer un dossier de candidature et assister le remplissage manuel de formulaires, sans auto-submit.

## Fonctionnalites

- import d'offres par CSV ou ajout manuel
- stockage local SQLite via SQLModel
- ranking explicable a partir d'un `profile.yaml`
- generation d'un application pack par offre
- aide au mapping de champs HTML vers des cles canoniques
- UI Streamlit pour parcourir, qualifier et traiter les offres

## Prerequis

- Python 3.11 ou plus recent
- Windows PowerShell, macOS Terminal ou shell Linux

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Copie ensuite l'exemple de profil:

```powershell
Copy-Item profile.example.yaml profile.yaml
```

## Lancement

Commande recommandee:

```powershell
python -m streamlit run src/app/main.py
```

Alternative si le script console est disponible dans ton `PATH`:

```powershell
app
```

Ne pas utiliser `python src/app/main.py`: ce fichier est un point d'entree Streamlit.

## Workflow type

1. Completer `profile.yaml` a partir de `profile.example.yaml`.
2. Importer des offres depuis l'UI ou le CLI:

```powershell
app ingest csv data/jobs.csv
app ingest add --title "Backend Engineer" --company "Acme" --url "https://example.test/job/1"
```

3. Ouvrir l'UI Streamlit, verifier les scores et filtrer les offres.
4. Ouvrir le detail d'une offre pour generer le pack de candidature.
5. Dans "Postuler (assiste)", coller le HTML du formulaire pour preparer le mapping des champs.
6. Copier manuellement les valeurs proposees. Aucun envoi automatique n'est effectue.

## Structure utile

- `src/app/main.py`: entree Streamlit
- `src/app/models/`: DB, tables, repositories
- `src/app/services/`: import, scoring, generation de pack, mapping de formulaire
- `src/app/templates/`: templates Jinja2 CV et lettre
- `data/`: base SQLite, mappings sauvegardes, packs generes

## Profil

Le projet cherche en priorite:

- `profile.yaml`
- `data/profile.yaml`

Voir `profile.example.yaml` pour le format attendu.

## Templates Jinja2

Les templates utilises par la generation de pack sont:

- `src/app/templates/lm/base.md.jinja`
- `src/app/templates/cv/base.md.jinja`

Ils peuvent etre personnalises tant qu'ils consomment le contexte `answers`, `profile` et `job`.

## Qualite et CI

Tests:

```powershell
python -m pytest
```

Lint:

```powershell
python -m ruff check .
```

Une CI GitHub Actions execute `pytest` et `ruff` a chaque push et pull request.
