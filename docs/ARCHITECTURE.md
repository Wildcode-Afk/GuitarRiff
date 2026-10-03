# GuitarRiff — Architecture proposée

> Statut : **proposition issue de l'audit (Étape 1)**. Aucun code n'existe encore.

## 1. Principes directeurs

1. **Pipeline à sens unique.** Chaque étape consomme la sortie de la précédente et produit un artefact bien défini et sérialisable (fichier ou enregistrement en base).
2. **`basic-pitch` est isolé.** Un seul module (`transcription/basic_pitch_adapter.py`) importe `basic_pitch`. Tout le reste du code dépend d'une interface `Transcriber` et d'un objet `NoteEvent`, pas de la bibliothèque elle-même. Cela permet de changer de moteur de transcription plus tard sans casser le reste.
3. **`librosa` est un outil d'analyse, pas un moteur de transcription.** Il sert au prétraitement (rééchantillonnage), à la séparation harmonique/percussive et à l'estimation de tempo/battements — jamais présenté comme équivalent à `basic-pitch` pour détecter les notes.
4. **`Song` (et ses `Track`/`NoteEvent`/`RhythmEvent`) est le contrat unique** entre toute méthode de transcription et tout le reste (mapping vers le manche, génération de tablature, export MIDI, frontend). **Le frontend ne dépend jamais directement du format de sortie d'un modèle d'IA** : un `Song` sérialisé (`model_dump_json()`) est tout ce qu'il reçoit. Modèle implémenté à l'Étape 8 (voir § 6 ci-dessous pour le détail des unités et conventions).
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
[6] Modèle musical commun (Song: pistes + NoteEvent[]/RhythmEvent[] + tempo/métrique)
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
│   │   ├── model/                # Song, Track, NoteEvent, RhythmEvent (contrats Pydantic — voir § ci-dessous)
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

## 6. Modèle musical commun (Song/Track/NoteEvent) — Étape 8

Implémenté dans `backend/guitarriff/model/` sous forme de modèles Pydantic v2
immuables (`model_config = ConfigDict(frozen=True)`) — cohérent avec le reste
du projet (déjà basé sur Pydantic/pydantic-settings), avec validation et
sérialisation JSON obtenues nativement, sans code manuel.

### Unités et conventions temporelles

| Donnée | Unité / convention |
|---|---|
| `NoteEvent.midi_pitch` | Hauteur MIDI standard (0-127, 60 = do central) |
| `NoteEvent.start_seconds` / `duration_seconds` | Secondes depuis le début de l'audio — **pas** une position en mesure/temps |
| `NoteEvent.velocity` | Vélocité MIDI standard (0-127) |
| `NoteEvent.confidence` | Optionnel, `[0.0, 1.0]` — `None` si la méthode de transcription n'en fournit pas |
| `TempoChange.bpm` | Battements **par noire**, quelle que soit la métrique active (convention MIDI/DAW standard, y compris en 6/8, 7/8, etc.) |
| `TempoChange.time_seconds` / `TimeSignatureChange.time_seconds` | Toujours ancrés en secondes absolues, **jamais** par numéro de mesure (qui dépendrait circulairement de l'historique tempo/métrique) |
| `MusicalPosition.bar` / `.beat` | Numérotés à partir de **1** (convention de notation musicale) ; `beat` est exprimé dans l'unité de la métrique active (ex. en 6/8 : 6 temps par mesure, pas 3) |
| `Track.tuning` | Séquence de hauteurs MIDI des cordes à vide, de la plus grave à la plus aiguë |

### Décisions de modélisation

- **`MusicalPosition` est une donnée dérivée**, jamais la source de vérité : un `NoteEvent` fraîchement transcrit a `position = None` ; `Song.with_computed_positions()` (fonction pure) la calcule pour toutes les notes/événements à partir de `tempo_changes`/`time_signature_changes`.
- **Les accords ne sont pas un objet dédié** : plusieurs `NoteEvent` dont les intervalles de temps se chevauchent, sur la même piste, constituent un accord. Le regroupement visuel est laissé à une étape de génération de tablature en aval.
- **Les silences ne sont pas des objets explicites** : un intervalle de temps sans `NoteEvent` est déjà un silence valide — convention identique à MIDI/`basic-pitch`, qui ne représentent que des événements note-on/note-off.
- **`RhythmEvent` (batterie) est distinct de `NoteEvent`** : un coup de batterie n'a pas de hauteur harmonique ; `RhythmEvent.drum_piece` utilise un vocabulaire contrôlé lisible (`DrumPiece`) plutôt qu'un numéro General MIDI Percussion brut. Sa `duration_seconds` peut valoir 0 (déclenchement instantané), contrairement à `NoteEvent` qui exige une durée strictement positive.
- **`InstrumentKind` est aligné sur les noms de pistes de la séparation (Étape 7)** : `drums`, `bass`, `other`, `vocals`, `guitar`, `piano` correspondent directement aux clés de `InstrumentKind` (`other` et `mixture` se rejoignent sur `InstrumentKind.OTHER`) — une piste séparée devient directement une `Track` sans table de correspondance ad hoc. Vérifié par un test de compatibilité dédié (`test_model_compatibility.py`).
- **Compatibilité multi-méthodes** : `confidence`, `instrument_info` et `tuning` sont tous optionnels — une méthode qui ne les fournit jamais (ex. import MIDI direct, sans confiance) produit des `Song` tout aussi valides qu'une méthode qui les fournit systématiquement (`basic-pitch`).

### Sérialisation

`Song.model_dump_json()` / `Song.model_validate_json(...)` (et leurs équivalents `model_dump`/`model_validate` pour un dict Python) sont le seul mécanisme de sérialisation — aucun code de conversion manuel. Les tuples (`notes`, `tracks`, `tempo_changes`, etc.) survivent au round-trip JSON grâce à la validation Pydantic native des types `tuple[X, ...]`.
