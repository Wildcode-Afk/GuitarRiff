# GuitarRiff

Application gratuite et open source qui transforme un lien YouTube ou un fichier
audio en tablatures, partitions et pistes musicales éditables (inspirée des
fonctionnalités de transcription de Songsterr).

> **Statut : fondations du projet (Étape 2).** Aucune fonctionnalité de
> transcription audio n'est encore implémentée. Voir `docs/` pour l'audit,
> l'architecture et les décisions techniques.

## Prérequis

- Python **3.11** (version épinglée dans `.python-version` — voir
  `docs/TECHNICAL_DECISIONS.md`, décision D1)
- [uv](https://docs.astral.sh/uv/) pour la gestion de l'environnement Python
- Node.js 22+ et npm (pour le frontend, à venir)
- FFmpeg installé sur le système (nécessaire dès l'étape de traitement audio)

## Installation

```bash
# Depuis la racine du projet
uv sync --extra dev
```

Cette commande crée un environnement virtuel `.venv` avec Python 3.11 et
installe le projet ainsi que les dépendances de développement (tests, lint,
typage).

## Configuration

```bash
cp .env.example .env
```

Éditer `.env` selon les besoins. Aucune valeur de `.env.example` n'est un
secret — voir ce fichier pour la description de chaque variable.

## Lancement (backend)

```bash
uv run uvicorn guitarriff.api.app:app --reload --host 127.0.0.1 --port 8000
```

Vérifier que l'application répond :

```bash
curl http://127.0.0.1:8000/health
```

Importer un fichier audio local (WAV, FLAC, OGG, M4A ou MP3) :

```bash
curl -X POST http://127.0.0.1:8000/audio-files -F "file=@/chemin/vers/mon_fichier.wav"
```

Importer l'audio d'une vidéo YouTube (usage personnel, sous votre
responsabilité — voir `docs/TECHNICAL_DECISIONS.md`, Q1) :

```bash
curl -X POST http://127.0.0.1:8000/youtube-imports \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=XXXXXXXXXXX"}'
```

Normaliser un fichier déjà importé vers le format interne (22050 Hz, mono —
voir `docs/API.md` pour la justification) :

```bash
curl -X POST http://127.0.0.1:8000/audio-files/<file_id>/normalize
```

Voir `docs/API.md` pour le détail des routes et des erreurs.

## Tests

```bash
uv run pytest
```

Les tests marqués `slow` ou `integration` (traitement audio réel, réseau) ne
sont jamais exécutés par défaut — voir `pyproject.toml`, section
`[tool.pytest.ini_options]`.

## Qualité de code

```bash
uv run ruff check .
uv run mypy backend/guitarriff
```

## Structure du projet

Voir `docs/ARCHITECTURE.md` pour le détail du pipeline et de l'arborescence
complète prévue. À ce stade, seuls les répertoires et fichiers de fondation
existent (pas encore de logique de transcription/tablature).

## Documentation

- `docs/PROJECT_STATUS.md` — état du projet, tenu à jour à chaque étape
- `docs/ARCHITECTURE.md` — architecture proposée et pipeline
- `docs/FEATURE_MATRIX.md` — classement des fonctionnalités (MVP / V2 / expérimental)
- `docs/TECHNICAL_DECISIONS.md` — décisions techniques justifiées et questions ouvertes
