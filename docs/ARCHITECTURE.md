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

## 7. Analyse rythmique et distinction détecté/manuel — Étape 10

`backend/guitarriff/rhythm/` : `analyzer.py` (seul point d'import de
`librosa`) détecte tempo, battements et changements de tempo avec une mesure
de confiance réelle ; `service.py` orchestre la mise à jour du `Song` déjà
persisté par la transcription (Étape 9) ou en crée un si nécessaire.

### `EstimationSource` — convention étendue au modèle commun (Étape 8)

`TempoChange` et `TimeSignatureChange` (voir § 6) portent désormais chacun un
champ `source: EstimationSource` (`DETECTED` ou `MANUAL`) et un champ
`confidence` optionnel (toujours `None` pour une valeur `MANUAL` — validé par
le modèle lui-même, pas seulement par convention). C'est la réponse directe à
l'exigence de distinguer une valeur estimée automatiquement d'une valeur
fournie ou corrigée par l'utilisateur : l'information vit dans le modèle, pas
seulement dans la couche API.

### Ce qui est détecté, ce qui est une convention par défaut

- **Tempo et battements** : détectés avec une vraie confiance mesurée (voir
  `docs/TECHNICAL_DECISIONS.md`, D8).
- **Métrique** : **jamais détectée depuis l'audio** à ce stade (aucune
  bibliothèque fiable retenue, voir D8). Une métrique 4/4 par défaut est
  appliquée avec `confidence=None` — qui signifie explicitement "hypothèse
  non analysée", pas "détectée avec une confiance nulle". Une correction
  manuelle (`POST .../time-signature`) est toujours prioritaire et n'est
  jamais écrasée par une nouvelle analyse automatique.
- **Mesures (bar starts)** : jamais détectées indépendamment non plus —
  dérivées de `compute_position` (§ 6) à partir du couple (tempo, métrique)
  retenu. Aucune logique de calcul de mesure dupliquée dans le module rythme.

## 8. Mapping manche (corde/case) — Étape 11

`backend/guitarriff/tablature/` remplit `NoteEvent.instrument_info` (champ
optionnel prévu dès l'Étape 8) : aucune modification du modèle commun n'a été
nécessaire, seulement un ajout symétrique de `NoteEvent.with_instrument_info`.

### Génération des positions candidates

Pour une hauteur MIDI `P`, toutes les cordes sont parcourues ; une position est
valide si `0 <= P - tuning[corde] - capo_fret <= max_fret - capo_fret`. Le
nombre de cordes est celui de `tuning` (aucune valeur codée en dur : guitare 6
ou 7 cordes, basse 4 ou 5 cordes, accordages alternatifs, etc.). Voir
`tablature/fretboard.py`.

### Sélection : fonction de coût, pas "première position valide"

`tablature/cost.py` combine quatre composantes, détaillées et justifiées dans
son docstring :

| Composante | Poids par défaut | Rôle |
|---|---|---|
| Déplacement | 1.0 par case | Distance à la position de main issue de la note/l'accord précédent (une corde à vide ne coûte rien : aucun doigt requis) |
| Écart entre les doigts (accord) | 2.0 par case | Plus pénalisant que le déplacement simple — un étirement est plus difficile qu'un changement de position |
| Jouabilité générale | 0.3 par case | Léger biais vers les cases basses |
| Bonus corde à vide | -0.5 | Une corde à vide est toujours plus facile à jouer |

**Ces poids sont un jugement heuristique de jouabilité, pas des constantes
dérivées objectivement** (contrairement par exemple à la fréquence
d'échantillonnage de l'Étape 6, justifiée par une contrainte vérifiable de
`basic-pitch`) : documentés comme tels, ajustables via `CostWeights`. **Le but
n'est pas de reconstituer le doigté réel du guitariste original** — ce qui est
impossible à déduire du seul audio — mais de produire une position jouable
cohérente avec ce qui précède.

Vérifié sur un cas réel : après une note en case 7, une note aux candidats
cases 2/7/12 reste en case 7 (déplacement nul) plutôt que de sauter à la case 2
pourtant plus basse en valeur absolue — preuve que la fonction de coût
l'emporte bien sur un simple "premier/plus bas candidat".

### Notes simultanées (accords)

`tablature/mapper.py` regroupe les notes dont les débuts diffèrent de moins de
50 ms (`CHORD_TOLERANCE_SECONDS` — une transcription audio réelle ne produit
presque jamais des `start_seconds` rigoureusement identiques pour les notes
d'un même accord) et résout le groupe par recherche exhaustive sous la
contrainte *une corde ne porte qu'une note à la fois*. La recherche exhaustive
reste largement praticable (accords de quelques notes, au plus
`n_strings` candidats par note).

### Notes impossibles à placer

Deux cas, tous deux signalés explicitement (`UnplacedNote.reason`) :
hauteur hors de portée (accordage/capodastre/limite de cases), ou plus de notes
simultanées jouables que de cordes disponibles (tout le groupe est alors
signalé, pas une sélection arbitraire).

## 9. Tablature de basse et rendu lisible — Étape 12

### Un mapper partagé, des profils par instrument

Plutôt que de copier le module guitare, la basse réutilise le même mapper
(`tablature/mapper.py`) paramétré par un **profil** (`tablature/profiles.py`) :
accordage par défaut, poids de la fonction de coût, durée de silence après
laquelle la position de la main est oubliée. `profile_for(instrument)` renvoie
`None` hors guitare/basse (décision Q3). Le profil guitare reproduit à
l'identique le comportement de l'Étape 11 (les 57 tests de cette étape passent
inchangés).

Ce qui est propre à la basse :

| Élément | Guitare | Basse | Raison |
|---|---|---|---|
| Déplacement (par case) | 1.0 | 1.5 | Cases plus larges, ligne quasi monophonique |
| Écart entre doigts (par case) | 2.0 | 3.0 | Un même écart est un étirement plus difficile |
| Jouabilité générale (par case) | 0.3 | 0.2 | Les cases hautes sont d'usage courant à la basse |
| Changement de corde (par corde) | 0 | 0.8 | Cordes très espacées, geste plus coûteux |
| Oubli de la position après silence | jamais | ≥ 1 s | Le bassiste a le temps de se repositionner |

**Ces valeurs sont un jugement heuristique, non validé contre de vraies lignes
de basse.** Mesure sur 300 lignes *simulées* (marche aléatoire de petits
intervalles, graine fixe) : le profil basse déplace moins la main (2514 cases
contre 2578) et change moins de corde (800 contre 834) que les poids guitare —
un effet réel mais modeste, sur des données synthétiques.

### Notes répétées, silences

- **Notes répétées** : le contexte de la note précédente (case de référence,
  corde moyenne) est conservé ; une note répétée reste exactement à la même
  position — propriété vérifiée sur 500 séquences aléatoires. Un bonus de
  répétition explicite a été **prototypé puis retiré** : sur 4000 séquences il
  ne changeait aucun résultat (le déplacement et le changement de corde
  suffisent), le garder aurait été du code mort.
- **Silences** : un silence n'est pas un objet du modèle (voir § 6) mais
  l'écart entre la fin d'un groupe et le début du suivant. Le seuil est
  inclusif (`≥ rest_reset_seconds`). Un test par mutation (règle désactivée)
  a confirmé que les tests de silence échouent bien sans elle.
- Le regroupement des notes simultanées travaille désormais sur des **indices**
  et non sur l'identité des objets, pour que des notes identiques ne
  s'écrasent pas.

### Extension du modèle commun : `Track.capo_fret`

Les numéros de case sont relatifs au capodastre ; pour relire ou afficher une
tablature il faut donc connaître celui-ci. `Track` porte désormais
`capo_fret` (défaut 0, rétrocompatible : un `Song` persisté avant cette étape
se charge toujours — testé).

### Rendu ASCII (`tablature/render.py`)

Fonction pure, **indépendante de l'instrument** (sert aussi la guitare), nombre
de cordes quelconque. Corde aiguë en haut, noms de cordes déduits de
l'accordage (`E A D G B e`), une colonne par note ou accord, retour à la ligne
selon `max_width`, barres de mesure issues des `MusicalPosition` (§ 6), colonnes
vides pour les silences d'au moins un temps (6 au plus).

**Limites assumées** : pas de notation rythmique (la largeur d'une colonne ne
dépend pas de la durée) ; la durée d'un temps vient du *premier* tempo du
`Song` (un changement de tempo ultérieur n'est pas répercuté sur l'espacement
des silences) ; un silence qui chevauche une barre de mesure est dessiné avant
cette barre ; les notes sans position ne sont pas affichées mais comptées et
signalées.
