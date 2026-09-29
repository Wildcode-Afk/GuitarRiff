# GuitarRiff — Architecture proposée

> Statut : **proposition issue de l'audit (Étape 1)**. Aucun code n'existe encore.

## 1. Principes directeurs

1. **Pipeline à sens unique.** Chaque étape consomme la sortie de la précédente et produit un artefact bien défini et sérialisable (fichier ou enregistrement en base).
2. **`basic-pitch` est isolé.** Un seul module (`transcription/basic_pitch_adapter.py`) importe `basic_pitch`. Tout le reste du code dépend d'une interface `Transcriber` et d'un objet `NoteEvent`, pas de la bibliothèque elle-même. Cela permet de changer de moteur de transcription plus tard sans casser le reste.
3. **`librosa` est un outil d'analyse, pas un moteur de transcription.** Il sert au prétraitement (rééchantillonnage), à la séparation harmonique/percussive et à l'estimation de tempo/battements — jamais présenté comme équivalent à `basic-pitch` pour détecter les notes.
4. **`NoteEvent` est le contrat unique** entre la transcription et tout le reste (mapping vers le manche, génération de tablature, détection d'accords, export MIDI, frontend).
5. **Fonctions pures autant que possible** pour le mapping, la génération de tab et la détection d'accords : entrée de données, sortie de données, aucune E/S — testables sans fichier audio réel.
6. **Aucun réseau dans les tests unitaires.** `yt-dlp` et `basic-pitch` sont simulés (mock/fake) à leur frontière ; les exécutions réelles sont marquées `slow`/`integration` et lancées à part.
7. **Abstraction de l'entrée.** Un job accepte soit une URL YouTube, soit un fichier audio importé. L'import de fichier est implémenté en premier : plus simple techniquement et plus sûr juridiquement (voir `TECHNICAL_DECISIONS.md`, Q1).

## 2. Stack technique proposée

| Couche | Choix | Justification |
|---|---|---|
| Langage backend | Python 3.11 | Requis par la contrainte TensorFlow de `basic-pitch` (voir `PROJECT_STATUS.md`) |
| Gestionnaire d'environnement | `uv` | Rapide, permet d'installer Python 3.11 même si le système a une autre version |
| Framework web | FastAPI + Uvicorn | Typage, async, documentation OpenAPI automatique |
| Modèles de données | Pydantic v2 | Validation + sérialisation JSON de `NoteEvent` |
| Récupération YouTube | `yt-dlp` (à valider — voir Q1) | Outil de facto pour ce cas d'usage, encapsulé derrière une interface remplaçable |
| Entrée/sortie audio | FFmpeg (système) + `soundfile`/`librosa` | Décoder n'importe quel format vers un WAV mono exploitable |
| Transcription | `basic-pitch` (isolé, backend TensorFlow) | Transcription polyphonique de notes ; seule bibliothèque open source mature pour ce rôle |
| Séparation d'instruments | `demucs` (à valider en conditions réelles — voir risques) | Séparation source-par-source avant transcription individuelle |
| MIDI | `pretty_midi` (déjà dépendance de `basic-pitch`) | Construction/lecture de fichiers MIDI |
| Stockage des jobs | Fichiers sous `data/jobs/<id>/` + SQLite | Pas de service externe à faire tourner pour un projet perso/open source |
| Exécution des jobs | File d'attente en mémoire, concurrence = 1 | Empreinte mémoire de TensorFlow/Demucs sur machine modeste |
| Tests backend | `pytest`, `pytest-cov` | Standard |
| Qualité de code | `ruff`, `mypy` | Lint + typage statique |
| Frontend | Vite + React + TypeScript | Client typé pour consommer l'API, cohérent avec un projet web moderne |
| Rendu de tablature | Composant SVG maison (évaluer `alphaTab` plus tard si besoin) | Contrôle total du rendu, pas de dépendance lourde imposée d'entrée |
| Lecture audio/MIDI dans le navigateur | Web Audio API (`Tone.js` si nécessaire) | Piloté par les données `NoteEvent`/MIDI |
| Tests frontend | Vitest + Testing Library, Playwright pour l'E2E | Standard écosystème Vite/React |
| Packaging | Docker | Reproduire l'environnement Python 3.11 + FFmpeg de façon fiable |

Le choix du frontend et de la bibliothèque de lecture audio sont des **propositions** modifiables sans impact sur le contrat du backend (`NoteEvent`).

## 3. Pipeline de traitement (vue d'ensemble)

```
Entrée (URL YouTube | fichier audio)
        │
        ▼
[1] Acquisition ──────────► fichier audio brut
        │
        ▼
[2] Normalisation (FFmpeg) ─► WAV mono, fréquence d'échantillonnage cible
        │
        ▼
[3] Séparation d'instruments (Demucs, optionnel/MVP+) ─► pistes séparées (guitare, basse, batterie, autres)
        │
        ▼
[4] Transcription par piste (basic-pitch) ─► NoteEvent[] par piste
        │
        ▼
[5] Analyse rythmique (librosa) ─► tempo, battements, mesures
        │
        ▼
[6] Modèle musical commun (Piece: pistes + NoteEvent[] + métadonnées rythmiques)
        │
        ├──► [7a] Génération de tablature guitare/basse (mapping manche)
        ├──► [7b] Export MIDI
        └──► [7c] Éditeur web (lecture, édition, export PDF)
```

## 4. Structure de répertoires proposée

```
GuitarRiff/
├── README.md
├── .gitignore
├── pyproject.toml
├── docs/
│   ├── PROJECT_STATUS.md
│   ├── ARCHITECTURE.md
│   ├── FEATURE_MATRIX.md
│   └── TECHNICAL_DECISIONS.md
├── backend/
│   ├── guitarriff/
│   │   ├── acquisition/        # yt-dlp adapter + upload handler
│   │   ├── audio/               # FFmpeg wrapper, normalisation
│   │   ├── separation/          # Demucs adapter
│   │   ├── transcription/       # basic_pitch_adapter.py (seul point d'import)
│   │   ├── rhythm/               # tempo/beat via librosa
│   │   ├── model/                # NoteEvent, Piece, contrats Pydantic
│   │   ├── tablature/            # mapping notes → manche, génération tab
│   │   ├── midi/                  # export/lecture MIDI
│   │   ├── jobs/                  # file d'attente, statuts
│   │   └── api/                   # routes FastAPI
│   └── tests/
│       ├── unit/
│       └── integration/          # marquées "slow", jamais en CI par défaut
└── frontend/
    ├── src/
    └── tests/
```

## 5. Points explicitement non tranchés à cette étape

- Acquisition audio YouTube : voir `TECHNICAL_DECISIONS.md`, Q1.
- Nécessité réelle de Demucs pour le MVP (ou report en V2) : voir `FEATURE_MATRIX.md`.
- Bibliothèque de rendu de tablature définitive (SVG maison vs `alphaTab`).
