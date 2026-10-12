# GuitarRiff — État du projet

## Étape 12 — Tablatures de basse (terminée le 08/10/2026)

> Statut : **mapping basse (4/5/6 cordes), notes répétées et silences gérés, rendu ASCII lisible. Mapper partagé avec la guitare (non copié) ; comportement guitare inchangé.**

### Ce qui a été ajouté

| Élément | État |
|---|---|
| `tablature/profiles.py` | `MappingProfile` (accordage par défaut, poids de coût, règle de silence) ; `GUITAR_PROFILE` (identique à l'Étape 11) et `BASS_PROFILE` ; `profile_for(instrument)` |
| `tablature/cost.py` | `CostWeights.string_change_weight` (0 par défaut → guitare inchangée), `string_center_after` ; `group_cost` accepte la corde de la note précédente |
| `tablature/mapper.py` | Contexte de main enrichi (case + corde), `rest_reset_seconds` (oubli de la position après un silence), regroupement par **indices** (des notes identiques ne s'écrasent plus), `group_simultaneous_notes` public |
| `tablature/fretboard.py` | Accordages `STANDARD_BASS_5_TUNING` (B E A D G) et `STANDARD_BASS_6_TUNING` (+ C) |
| `tablature/render.py` | Rendu ASCII : cordes nommées d'après l'accordage, corde aiguë en haut, colonnes par note/accord, silences, barres de mesure, retour à la ligne, notes sans position comptées. Indépendant de l'instrument |
| `model/track.py` | `Track.capo_fret` (défaut 0, rétrocompatible — testé avec un `Track` « ancien format ») |
| `map-fretboard` | Choisit le profil selon `instrument` ; le message mentionne « bassiste » / « guitariste » |
| `GET /audio-files/{id}/tablature` | Nouvelle route, lecture seule ; erreur `409 fretboard_not_mapped` si le mapping n'a pas été fait |
| Tests | **71 nouveaux tests** (accordages 4/5/6 cordes et drop D, limites de cases, changements de position, séquences, répétitions, silences, notes impossibles, rendu exact, service, API) — backend à **435 tests par défaut + 3 d'intégration** |

### Vérifications réelles effectuées (pas supposées)

- **Le profil basse change réellement les résultats** : cas concret trouvé par recherche exhaustive sur les séquences de 3 notes — pour `33 37 39`, la basse garde la ligne sur la corde de la (cases 0, 4, 6) là où les poids guitare sautent à la corde de ré (case 1). 123 séquences (trois hauteurs distinctes entre 33 et 49) donnent un résultat différent.
- **Mesure sur 300 lignes simulées** (graine fixe) : le profil basse déplace moins la main (2514 cases contre 2578) et change moins de corde (800 contre 834). Effet réel mais **modeste, et mesuré sur des données synthétiques**, pas sur de vraies lignes de basse.
- **Un élément retiré parce qu'inutile** : j'avais prototypé un bonus de répétition (rejouer une note identique à la même position). Mesuré sur 4000 séquences aléatoires avec répétitions : **aucun résultat modifié**, et les notes répétées ne bougeaient déjà jamais sans lui. Retiré plutôt que gardé comme code mort ; la propriété « une note répétée ne change jamais de position » est testée à la place (500 séquences aléatoires).
- **Test par mutation** : en désactivant la règle de silence, les deux tests de silence concernés échouent (et passent à nouveau une fois la règle restaurée) — ils ne sont donc pas vides.
- **Scénario de silence vérifié** : après une note en case 9, une note aux candidats cases 13/8/3 reste en case 8 si le silence est de 0,2 s, mais passe en case 3 après 3 s.
- **Deux de mes attentes de test étaient fausses, pas le code** : j'avais oublié que des colonnes vides s'insèrent pour les silences d'au moins un temps, et qu'une barre de mesure s'insère entre deux notes de mesures différentes (4/4 à 120 BPM = 2 s par mesure). Attentes corrigées après avoir lu le détail des échecs.

### Respect des consignes

- **Pas de copie aveugle** : un seul mapper, des profils ; les 57 tests de guitare de l'Étape 11 passent inchangés.
- **Notes impossibles détectées** : hauteur sous la corde la plus grave (ex. B0 sur 4 cordes, jouable sur 5), plus de notes simultanées que de cordes — signalées avec leur raison, et comptées dans le rendu.
- **Ne prétend pas reconstituer le jeu d'un bassiste** : rappelé dans `notes` de chaque réponse.

### Écarts honnêtes

- **Poids du profil basse = jugement heuristique**, jamais validé contre de vraies lignes de basse (aucun corpus utilisé) ; documenté comme tel dans `profiles.py` et `docs/ARCHITECTURE.md` § 9.
- **Le rendu ne représente pas les durées** (pas de notation rythmique) ; la durée d'un temps vient du *premier* tempo du `Song`, un changement de tempo ultérieur n'est donc pas répercuté sur l'espacement des silences ; un silence qui chevauche une barre de mesure est dessiné avant cette barre.
- **Seuil de silence (1 s) fixe**, indépendant du tempo : un choix pragmatique, pas une durée musicale.
- Les barres de mesure ne sont aussi fiables que la carte de tempo/métrique du `Song` (métrique 4/4 par défaut non confirmée tant que l'utilisateur ne la corrige pas, Étape 10).
- Le mapping n'est toujours pas rejoué automatiquement après une nouvelle transcription.
- Le rendu des mêmes notes n'a été validé visuellement que sur quelques exemples (dont celui de `docs/API.md`), pas sur de longues transcriptions réelles.

### Résultats d'exécution réels

```
Backend : uv run pytest                → 435 passed, 3 deselected
Backend : uv run ruff check .          → All checks passed!
Backend : uv run mypy backend/guitarriff → Success: no issues found in 53 source files
```

## Historique — Étape 11 : génération des tablatures de guitare (06/10/2026)

> Statut : **conversion notes → positions (corde, case) fonctionnelle, avec fonction de coût réelle (pas "première position valide"). Ne prétend pas reconstituer le doigté original du guitariste.**

### Ce qui a été ajouté

| Élément | État |
|---|---|
| `tablature/fretboard.py` | `FretboardConfig` (accordage, capodastre, limite de cases) et génération des positions candidates ; nombre de cordes = longueur du tuning fourni (guitare 6/7 cordes, basse 4/5, accordages alternatifs) |
| `tablature/cost.py` | Fonction de coût : déplacement par rapport à la position précédente, écart entre les doigts (accords), jouabilité générale, bonus corde à vide — heuristique documentée, poids ajustables |
| `tablature/mapper.py` | Groupement des notes simultanées (tolérance 50 ms), résolution exhaustive sous contrainte de cordes distinctes, signalement explicite des notes impossibles |
| `tablature/service.py` | Orchestration sur le `Song` persisté (Étape 9), remplit `instrument_info` et `Track.tuning` |
| `POST /audio-files/{id}/map-fretboard` | Nouvelle route — `instrument`, `tuning`, `capo_fret`, `max_fret` configurables |
| `NoteEvent.with_instrument_info` | Ajout symétrique de `with_position` (Étape 8) — aucun changement du modèle commun lui-même, `instrument_info` existait déjà (optionnel) |
| Tests | **57 nouveaux tests** : notes simples, accords, changements de position, accordages différents (basse, drop D, 7 cordes), capodastre, notes impossibles — backend à **364 tests par défaut + 3 d'intégration** |

### Vérifications réelles effectuées avant d'écrire les tests (pas supposées)

- **Note simple** (A4/440 Hz, MIDI 69) : plusieurs positions valides sur 5 cordes ; la corde aiguë, case 5, est choisie plutôt que la première trouvée (corde grave, case 24) — la fonction de coût a bien un effet.
- **Accord power chord** (MIDI 40+47) : corde à vide basse + case 2 de la corde suivante — voicing que choisirait naturellement un guitariste.
- **Capodastre** : j'ai d'abord écrit à tort un test où un capodastre rendait une note plus grave jouable ; l'exécution réelle a montré l'inverse (un capodastre *élève* la hauteur minimale atteignable). Test corrigé, comportement du code correct dès le départ.
- **Cohérence de déplacement** : recherche programmatique d'un cas où la meilleure position n'est pas la plus basse — trouvé (pitch 52, références 7.0) et converti en test : la case 7 (déplacement nul) l'emporte sur la case 2.
- **Basse 4 cordes, accord de 5 notes** : les 5 notes sont signalées comme impossibles, avec la raison, plutôt que d'en garder 4 arbitraires.

### Respect des consignes de conformité

- **Pas de "première position valide"** : testé explicitement (`test_does_not_always_pick_the_first_candidate_string`, `test_sequence_prefers_staying_near_previous_position`).
- **Ne prétend pas reconstituer le doigté original** : documenté dans `docs/ARCHITECTURE.md` § 8 et rappelé dans le champ `notes` de chaque réponse API.
- **Notes impossibles signalées, jamais ignorées silencieusement** : elles restent dans la piste avec `instrument_info: null` et leur raison est listée.

### Écarts honnêtes

- **Les poids de la fonction de coût sont un jugement heuristique**, pas des constantes dérivées objectivement — documenté comme tel, mais jamais validé contre des doigtés de guitaristes réels (aucun jeu de données de référence n'a été utilisé).
- **Les accords sont regroupés par proximité temporelle des débuts de note (50 ms)** : deux notes d'un même accord qui seraient transcrites avec un écart supérieur seraient traitées comme séparées, et inversement.
- **La position de référence de la main est une moyenne simple des cases pressées** — simplification volontaire, pas un modèle biomécanique de la main.
- Le mapping n'est pas rejoué automatiquement quand une transcription est refaite : à relancer explicitement après chaque nouvelle transcription.

### Résultats d'exécution réels

```
Backend : uv run pytest                → 364 passed, 3 deselected
Backend : uv run ruff check .          → All checks passed!
Backend : uv run mypy backend/guitarriff → Success: no issues found in 51 source files
Frontend : npm run test                → 1 passed (inchangé)
```

## Historique — Étape 10 : analyse rythmique (04/10/2026)

> Statut : **tempo et battements détectés réellement avec confiance mesurée. Métrique jamais déduite — convention 4/4 par défaut, corrections manuelles entièrement supportées et distinguées du détecté.**

### Étude des bibliothèques (avant implémentation, comme demandé)

| Bibliothèque | Constat |
|---|---|
| `librosa` (retenue) | Déjà installée (dépendance transitive de basic-pitch, aucun coût d'ajout). Détection tempo/battements robuste et bien établie. **Aucun détecteur de métrique fiable intégré.** |
| `madmom` (écartée) | Référence historique pour le suivi de métrique/downbeat, mais paquet PyPI non maintenu depuis plusieurs années, extensions Cython compilées difficiles à installer sur Python/NumPy récents (constat indépendant) |
| `madmom-infer` (notée, non retenue) | Réimplémentation 2026 pure NumPy/SciPy de madmom, maintenue — mais projet jeune et spécialisé ; ajout non jugé justifié pour cette étape (voir docs/TECHNICAL_DECISIONS.md, D8) |

### Vérifications réelles effectuées (pas supposées)

- Click track synthétique à 120 BPM → tempo détecté 117.5 BPM (écart ~2 %, caractéristique connue de l'algorithme sur un signal de clics purs, documentée).
- Bruit blanc (aucun rythme réel) → confiance ~0.23, contre ~1.0 sur un signal rythmique régulier : la mesure de confiance distingue effectivement un vrai rythme d'un signal sans rythme.
- Introduction silencieuse de 2s avant le contenu → tempo toujours détecté correctement, premier battement situé après le silence.
- Signal à deux tempos connus (120 puis 90 BPM) → changement de tempo correctement détecté par analyse en fenêtres glissantes.
- Silence complet → `beat_track` renvoie un tempo de 0.0 et aucun battement : traité explicitement comme "aucun rythme détecté" (`422 no_rhythm_detected`), jamais comme un tempo de substitution fabriqué.

### Ce qui a été ajouté

| Élément | État |
|---|---|
| `model/tempo.py` (extension Étape 8) | `TempoChange`/`TimeSignatureChange` portent désormais `source` (`EstimationSource.DETECTED`/`MANUAL`) et `confidence` — validé : `confidence` doit être `None` pour une valeur `MANUAL` |
| `rhythm/analyzer.py` | Seul point d'import de `librosa` ; tempo, battements, confiance, segments de tempo (changements) |
| `rhythm/service.py` | Orchestration : crée/met à jour le `Song` (réutilise la persistance de l'Étape 9), applique une métrique 4/4 par défaut non confirmée, préserve une métrique manuelle existante lors d'une ré-analyse |
| `POST /audio-files/{id}/analyze-rhythm` | Détection automatique |
| `POST /audio-files/{id}/tempo` | Correction manuelle du tempo |
| `POST /audio-files/{id}/time-signature` | Correction manuelle de la métrique (dénominateur validé comme puissance de 2) |
| Tests | **56 nouveaux tests**, avec exemples synthétiques à tempo/métrique connus et cas ambigus (silence, bruit blanc, signal trop court, introduction silencieuse) — backend à **307 tests par défaut + 3 d'intégration** |

### Respect des consignes de conformité

- **Jamais de métrique certaine déduite d'une estimation incertaine** : aucune détection de métrique n'est tentée ; la valeur par défaut porte `confidence: null`, explicitement distincte d'une détection à faible confiance.
- **Détecté vs manuel toujours distingué** dans le modèle lui-même (`EstimationSource`), pas seulement documenté en prose.
- **Introductions, silences, mesures incomplètes** gérés : testés explicitement (intro silencieuse, silence complet, signal court) ; les mesures incomplètes ne posent pas de problème structurel puisque `compute_position` (Étape 8) fonctionne pour n'importe quel instant, sans exiger une fin de morceau alignée sur une limite de mesure.
- **Représentation temporelle cohérente avec le modèle commun** : `analyze-rhythm` produit directement des `TempoChange`/`TimeSignatureChange` du modèle de l'Étape 8, aucune structure parallèle.

### Écarts honnêtes

- Comme pour les étapes précédentes, le timeout est "honnête" (borne l'attente côté appelant via un thread).
- La détection de changement de tempo utilise une analyse par fenêtres de 6 s avec un seuil de 8 % — un choix pragmatique vérifié empiriquement sur un cas à deux tempos connus, pas une méthode de pointe (ex. suivi de tempo dynamique échantillon par échantillon).
- Les "mesures"/débuts de mesure ne sont jamais indépendamment détectés depuis l'audio (pas de downbeat tracker) — toujours dérivés du couple tempo/métrique retenu, qui peut lui-même reposer sur une métrique par défaut non confirmée.

### Résultats d'exécution réels

```
Backend : uv run pytest                → 307 passed, 3 deselected
Backend : uv run ruff check .          → All checks passed!
Backend : uv run mypy backend/guitarriff → Success: no issues found in 46 source files
Frontend : npm run test                → 1 passed (inchangé)
```

## Historique — Étape 9 : transcription des notes avec basic-pitch (03/10/2026)

> Statut : **première transcription réelle et fonctionnelle de bout en bout. basic-pitch installé pour de vrai (pas seulement vérifié), inférence réelle exécutée et vérifiée.**

### Vérification préalable (avant implémentation, comme demandé)

Confirmée par une **installation et une exécution réelles** dans l'environnement du projet (pas une relecture de l'audit de l'Étape 1) :

- Python 3.11 requis (incompatible 3.12) — confirmé à nouveau.
- `setuptools<81` nécessaire en complément de `basic-pitch[tf]` — confirmé à nouveau.
- **Inférence réelle exécutée** : une sinusoïde à 440 Hz générée par FFmpeg produit bien une note détectée à la hauteur MIDI 69 (A4) — vérifié manuellement avant d'écrire les tests, puis couvert par un test d'intégration réel.
- Audio silencieux → liste de notes vide (pas une erreur) — vérifié réellement.
- Fichier inexistant → `FileNotFoundError` ; fichier audio corrompu → `EOFError` — ces deux comportements réels de basic-pitch ont guidé la conception de la gestion d'erreurs.

### Ce qui a été ajouté

| Élément | État |
|---|---|
| `transcription/basic_pitch_adapter.py` | **Seul point d'import de `basic_pitch`** (même principe d'isolation que Demucs). `basic-pitch[tf]` est désormais une dépendance **requise** du projet (pas optionnelle comme Demucs) — c'est le moteur du MVP |
| `transcription/converter.py` | Conversion pure des notes brutes vers `NoteEvent` (modèle de l'Étape 8) ; `amplitude` → `velocity` MIDI + `confidence`, filtrage défensif des durées nulles/négatives |
| `transcription/service.py` | Orchestration : résolution de la source (mélange normalisé ou piste séparée), limite de temps, mise à jour du `Song` persisté (remplacement par instrument, pas d'accumulation en double) |
| `POST /audio-files/{id}/transcribe` | Nouvelle route — `instrument` limité à guitare/basse (décision Q3), `source` = mélange ou piste séparée |
| `GET /audio-files/{id}/song` | Nouvelle route — le `Song` persisté, premier usage concret du contrat de l'Étape 8 |
| `GET /health?verbose=true` | Ajoute `checks.basic_pitch_available` |
| `pyproject.toml` | `addopts` corrigé pour **réellement** exclure `slow`/`integration` par défaut (déclarés depuis l'Étape 2 mais jamais appliqués faute de tests ainsi marqués jusqu'ici) |
| `docs/MODELS.md` | Nouvelle section basic-pitch : vérification, limites de transcription à communiquer à l'utilisateur |
| Tests | **38 nouveaux tests**, dont **3 tests d'intégration réels** (modèle basic-pitch réellement exécuté, exclus de la suite par défaut, lancés via `pytest -m integration`) — backend à **279 tests par défaut + 3 d'intégration** |

### Respect des consignes de conformité

- **Jamais de faux résultat** : un échec (timeout, erreur interne, fichier invalide) renvoie toujours une erreur claire, jamais une piste vide ou approximative substituée silencieusement.
- **Limites honnêtement documentées** : `docs/MODELS.md` et le champ `notes` systématiquement renvoyé par l'API rappellent que basic-pitch ne reconnaît jamais parfaitement un instrument dans un mélange complet.
- **Préférence pour les pistes séparées** : le paramètre `source` de `/transcribe` permet explicitement d'utiliser une piste déjà séparée (Étape 7) plutôt que le mélange complet, avec une recherche automatique `htdemucs_6s` puis `htdemucs` pour un nom de piste donné.

### Écarts honnêtes

- Comme pour yt-dlp et Demucs, le timeout de transcription est un timeout "honnête" (borne l'attente côté appelant via un thread, pas un arrêt forcé).
- La transcription est synchrone (pas de progression exposée comme pour la séparation) : la tâche ne l'exigeait pas explicitement, et une inférence basic-pitch sur un extrait court reste nettement plus rapide qu'une séparation Demucs complète.
- `instrument_info` (corde/case) des `NoteEvent` produits reste `None` : basic-pitch ne fournit que la hauteur, pas de mapping manche — toujours en attente d'une étape ultérieure.
- Un bug préexistant a été corrigé au passage : les marqueurs pytest `slow`/`integration`, déclarés depuis l'Étape 2, n'étaient en réalité jamais appliqués (aucun `-m "not slow and not integration"` dans `addopts`) faute d'avoir eu, jusqu'à cette étape, des tests réellement marqués ainsi.

### Résultats d'exécution réels

```
Backend : uv run pytest                → 279 passed, 3 deselected
Backend : uv run pytest -m integration → 3 passed, 279 deselected
Backend : uv run ruff check .          → All checks passed!
Backend : uv run mypy backend/guitarriff → Success: no issues found in 43 source files
Frontend : npm run test                → 1 passed (inchangé)
```

## Historique — Étape 8 : modèle musical commun (03/10/2026)

> Statut : **modèle de données central implémenté, validé, sérialisable — le contrat unique pour toute future méthode de transcription. Toujours aucune transcription réelle branchée.**

### Ce qui a été ajouté

| Élément | État |
|---|---|
| `model/song.py` | `Song` (racine) + `AudioMetadata` — valide que `tempo_changes`/`time_signature_changes` commencent à `time_seconds=0.0` et sont strictement croissants, identifiants de piste uniques |
| `model/track.py` | `Track` + `TrackDisplaySettings` (couleur hexadécimale validée, clé, ordre d'affichage) |
| `model/note_event.py` | `NoteEvent` + `InstrumentSpecificInfo` (corde/case, toujours optionnels) |
| `model/rhythm_event.py` | `RhythmEvent` pour la batterie — vocabulaire contrôlé `DrumPiece`, durée nulle autorisée |
| `model/tempo.py` | `TempoChange`, `TimeSignatureChange` — dénominateur validé comme puissance de 2 |
| `model/position.py` | `MusicalPosition` + `compute_position` (fonction pure, gère changements de tempo et de métrique) |
| `model/enums.py` | `InstrumentKind` (aligné sur les noms de pistes de la séparation, Étape 7), `Clef`, `DrumPiece` |
| Tests | **95 nouveaux tests** — validation, immutabilité, sérialisation round-trip, calcul de position (scénarios vérifiés à la main), compatibilité multi-méthodes — backend à **250 tests au total** |
| `docs/ARCHITECTURE.md` | Section 6 ajoutée (unités, conventions, décisions de modélisation) ; renommage `Piece` → `Song` dans le reste du document |

### Vérifications réelles effectuées

- `compute_position` vérifié par calcul manuel avant d'écrire les tests formels (ex. 120 BPM 4/4 : 1 mesure = 2.0s exactement ; changement de tempo à mi-mesure ; changement de métrique ; métrique composée 6/8).
- Round-trip JSON complet d'un `Song` réaliste à 3 pistes (guitare avec accord, basse, batterie) avec changement de tempo — reconstruction strictement identique à l'original (`restored == song`).
- Test de compatibilité avec deux formes de sortie différentes (façon `basic-pitch` avec confiance, façon import MIDI sans confiance) : les deux produisent des `Song` valides sans traitement spécial.
- Test de cohérence croisée avec l'Étape 7 : chaque nom de piste de séparation (`drums`, `bass`, `other`, `vocals`, `guitar`, `piano`) a un `InstrumentKind` correspondant.

### Écarts honnêtes

- Ce modèle n'est pas encore branché à une vraie transcription : aucun `Song` n'est encore produit par l'application elle-même (prochaine étape).
- Le calcul de position (`compute_position`) suppose que les changements de métrique interviennent sur une limite de mesure pour un résultat parfaitement intuitif ; si ce n'est pas le cas, l'algorithme reste déterministe mais le changement de taille de mesure s'applique au prorata, sans réalignement rétroactif.
- `InstrumentSpecificInfo` (corde/case) n'est renseigné par rien à ce stade — en attente de l'étape de mapping manche.

### Résultats d'exécution réels

```
Backend : uv run pytest        → 250 passed
Backend : uv run ruff check .  → All checks passed!
Backend : uv run mypy backend/guitarriff → Success: no issues found in 39 source files
Frontend : npm run test        → 1 passed (inchangé)
```

## Historique — Étape 7 : séparation d'instruments (02/10/2026)

> Statut : **module de séparation fonctionnel et testé (mocks), Demucs en dépendance optionnelle non installée dans cet environnement. Validation en conditions réelles encore à faire — voir écarts honnêtes.**

### Vérification préalable (avant implémentation, comme demandé)

| Critère | Constat |
|---|---|
| Licence du **code** Demucs | **MIT**, confirmé par plusieurs sources indépendantes (PyPI, dépôt officiel, distributions tierces) |
| Licence des **poids pré-entraînés** | **Nuancée, non définitivement tranchée publiquement** — l'auteur aurait indiqué dans des discussions GitHub que les poids sont fournis "à des fins de recherche" (conditions du jeu de données MusDB), malgré des métadonnées "MIT" incohérentes vues sur certaines pages de modèles. Documenté en détail, sans trancher à la place de l'utilisateur, dans `docs/MODELS.md` |
| Compatibilité Python 3.11 | Confirmée (métadonnées PyPI : `demucs>=4.0` nécessite `python>=3.10`, `torch>=2.1`, wheels `cp311` disponibles) |
| Installation réelle testée | **Non réalisable dans ce bac à sable** : `torch` depuis l'index PyPI par défaut entraîne toute la pile CUDA (vérifié par résolution de dépendances réelle, plusieurs Go), et l'index CPU dédié de PyTorch (`download.pytorch.org`) n'est pas accessible depuis le réseau de cet environnement. Recommandation d'installation documentée dans `docs/MODELS.md` |

### Ce qui a été ajouté

| Élément | État |
|---|---|
| `separation/capabilities.py` | Détection CPU/mémoire (`/proc/meminfo`, aucune dépendance ajoutée)/torch/demucs/CUDA — aucune supposition, lu réellement |
| `separation/models.py` | 3 modes : `none`, `htdemucs` (4 pistes), `htdemucs_6s` (6 pistes, expérimental) — limites connues documentées dans chaque réponse API |
| `separation/progress.py` | Suivi de progression en mémoire, par étapes (queued → loading_model → separating → writing_stems → done/error) |
| `separation/engine.py` | **Seul point d'import de `torch`/`demucs`** (même principe d'isolation que `basic-pitch`) ; dépendance optionnelle, absence gérée proprement |
| `separation/service.py` | Orchestration : cache disque (évite de relancer inutilement), vérification mémoire, vérification de durée, exécution en arrière-plan, détection de concurrence |
| `POST/GET /audio-files/{id}/separate[/{mode}]` | Nouvelles routes, + téléchargement de piste individuelle |
| `GET /health?verbose=true` | Ajoute `checks.separation` (capacités détectées) |
| `pyproject.toml` | Extra optionnel `separation` (Demucs), **volontairement séparé de `dev`** — pas installé par défaut |
| `docs/MODELS.md` | Nouveau document : installation, avertissement CUDA vérifié, limites de chaque mode, section licence complète |
| Tests | 33 nouveaux tests — backend à **155 tests au total** |

### Stratégie de test (conforme à la consigne "sans télécharger un gros modèle")

- **Capacités, modèles, progression** : tests unitaires classiques, rapides.
- **Moteur (`engine.py`)** : le cas "Demucs non installé" est testé **réellement, sans aucun mock** — cette dépendance optionnelle est absente de l'environnement de test, ce qui permet de vérifier pour de vrai le comportement attendu en son absence, sans réseau ni téléchargement. Les cas "Demucs installé" (succès, échec de chargement du modèle, échec de la séparation elle-même) sont simulés via un faux point d'import.
- **Service** : fichiers audio réels générés par FFmpeg (comme à l'Étape 6), moteur simulé. Couvre le cache, la mémoire insuffisante, la durée trop longue, l'exécution concurrente, la progression, le timeout (simulé en manipulant directement l'horodatage de départ, sans attendre pour de vrai).
- **API** : un test d'intégration bout-en-bout **sans aucun mock** vérifie que l'absence réelle de Demucs est gérée proprement jusqu'à la réponse HTTP (`stage: "error"`, message clair), sans jamais nécessiter de téléchargement.

### Écarts honnêtes (importants pour cette étape)

1. **L'intégration Demucs elle-même n'a pas pu être exécutée contre une vraie installation** dans ce bac à sable (contrainte réseau/disque, voir `docs/MODELS.md`). Le code suit l'API Python documentée par Demucs, mais doit être validé en conditions réelles avant mise en production.
2. **Licence des poids pré-entraînés non tranchée** — documentée honnêtement dans `docs/MODELS.md`, recommandation d'usage personnel uniquement tant que la question n'est pas clarifiée pour un usage commercial/de redistribution.
3. **Détection de cache local des modèles non implémentée** : `SEPARATION_ALLOW_MODEL_DOWNLOAD=false` refuse tout chargement plutôt que de vérifier si le modèle est déjà présent — nous n'avons pas pu vérifier de façon fiable l'emplacement de ce cache dans cet environnement.
4. **Timeout "honnête"**, comme pour yt-dlp (Étape 5) : borne l'état visible côté client, pas une extinction forcée du thread sous-jacent.
5. **Progression grossière, par paliers** (pas un pourcentage continu fin) : nous n'avons pas pu vérifier de façon fiable une éventuelle API de callback interne plus précise de Demucs dans cet environnement.
6. **État de progression en mémoire** (process unique) : perdu en cas de redémarrage pendant un calcul en cours ; le cache sur disque, lui, survit.

### Résultats d'exécution réels

```
Backend : uv run pytest        → 155 passed
Backend : uv run ruff check .  → All checks passed!
Backend : uv run mypy backend/guitarriff → Success: no issues found in 32 source files
Frontend : npm run test        → 1 passed (inchangé)
```

## Historique — Étape 6 : préparation et normalisation audio (01/10/2026)

> Statut : **normalisation FFmpeg fonctionnelle, testée avec de vrais fichiers audio. Toujours aucune transcription.**

### Choix du format cible — vérifié, pas deviné

Format retenu : **22050 Hz, mono, PCM 16 bits.** Justification concrète,
vérifiée directement dans l'environnement du projet (pas une convention
supposée) :

```
$ grep -n "AUDIO_SAMPLE_RATE\|AUDIO_N_CHANNELS" basic_pitch/constants.py
31:AUDIO_SAMPLE_RATE = 22050
32:AUDIO_N_CHANNELS = 1
```

`basic-pitch` — le modèle de transcription retenu pour le MVP (guitare/basse,
décision Q3) — impose ces deux valeurs dans son propre code source. Le PCM 16
bits est retenu pour le conteneur intermédiaire car la bibliothèque de
chargement audio qu'utilise `basic-pitch` en interne reconvertit de toute
façon tout flux en flottant normalisé à la lecture : un conteneur 16 bits
(96 dB de plage dynamique) est donc amplement suffisant sans gain de
précision mesurable, et évite de doubler la taille des fichiers
intermédiaires pour rien. Si Demucs (séparation d'instruments, V2) est
ajouté plus tard, il aura probablement besoin de 44100 Hz stéréo : ce n'est
pas anticipé ici, un réglage dédié sera fait à ce moment-là plutôt que de
deviner aujourd'hui une contrainte non encore confirmée.

### Ce qui a été ajouté

| Élément | État |
|---|---|
| `audio/ffmpeg.py` | Détection de disponibilité FFmpeg/ffprobe, lecture de métadonnées réelles (`probe_audio`), conversion vers le format cible (`normalize_audio`) — toujours via liste d'arguments, jamais de shell |
| `audio/service.py` | Orchestration : vérifie la durée réelle avant conversion, persiste le résultat dans les métadonnées du fichier stocké |
| `POST /audio-files/{id}/normalize` | Nouvelle route ; réutilise le fichier déjà stocké (upload local ou YouTube) |
| `GET /health?verbose=true` | Ajoute `checks.ffmpeg_available` |
| Nouveaux champs de métadonnées | `duration_seconds`, `normalized`, `normalized_sample_rate`, `normalized_channels` sur `StoredAudioFile`/`AudioFileMetadata` |
| Nouvelle limite | `AUDIO_MAX_DURATION_SECONDS` (20 min par défaut), appliquée uniformément à tout audio (local ou YouTube) au moment de la normalisation |
| Nettoyage | Écriture dans `normalized.wav.tmp` puis renommage atomique — aucun fichier partiel laissé en cas d'échec ou de timeout (vérifié par test) |
| Tests | 21 nouveaux tests, **avec de vrais fichiers audio générés par FFmpeg** (sinusoïdes 44100 Hz stéréo) pour les cas valides, et des pannes FFmpeg simulées (timeout, échec, code shell inspecté) pour les cas d'erreur — backend à **115 tests au total** |

### Vérifications réelles effectuées

- `probe_audio` sur un vrai fichier généré (2 s, 44100 Hz, stéréo) : durée, fréquence et nombre de canaux correctement lus.
- `normalize_audio` sur ce même fichier : sortie effectivement à 22050 Hz mono (reprobée pour confirmer, pas supposée).
- Fichier WAV avec en-tête valide mais corps tronqué (passe la détection par contenu de l'Étape 4, mais pas une lecture réelle) : rejeté à la normalisation (`invalid_audio_file`), ni avant.
- Panne FFmpeg simulée (code de sortie non nul, timeout) : erreur propre renvoyée, **aucun fichier `.tmp` résiduel** dans les deux cas (vérifié par test).
- Absence de FFmpeg simulée (`shutil.which` neutralisé) : `503 ffmpeg_unavailable`, y compris via l'API complète.

### Écarts honnêtes

- Comme aux étapes précédentes, l'avertissement `httpx`/`TestClient` persiste, toujours sans impact.
- La normalisation doit être déclenchée explicitement (`POST .../normalize`) ; elle n'est pas encore automatique après l'upload ou l'import YouTube — ce sera naturel de l'enchaîner à l'étape de transcription.
- Toujours aucune transcription : conforme à la consigne de cette étape.

### Résultats d'exécution réels

```
Backend : uv run pytest        → 115 passed
Backend : uv run ruff check .  → All checks passed!
Backend : uv run mypy backend/guitarriff → Success: no issues found in 26 source files
```

## Historique — Étape 5 : acquisition depuis YouTube (30/09/2026)

> Statut : **import YouTube fonctionnel, sécurisé, testé sans réseau. Toujours aucune transcription.**

### Vérification préalable de `yt-dlp` (avant implémentation, comme demandé)

| Critère | Constat |
|---|---|
| Maintenance | Très active : releases quasi quotidiennes (dernière vérifiée : `2026.08.19`, canaux stable/nightly/master) |
| Licence | **Unlicense** (domaine public) — aucune incompatibilité avec le reste du projet |
| Dépendances | Légères : `requests`, `certifi`, `websockets`, `mutagen`, `pycryptodomex`, `brotli` — aucun conflit avec les dépendances existantes (notamment aucun chevauchement avec la contrainte TensorFlow de `basic-pitch`) |
| Sécurité | 0 vulnérabilité connue au moment de la vérification |
| Installation réelle | Testée dans l'environnement du projet (`uv sync`) — fonctionne sous Python 3.11 sans ajustement |

### Ce qui a été ajouté

| Élément | État |
|---|---|
| `acquisition/youtube_url.py` | Validation stricte des URL (hôtes YouTube connus uniquement) et normalisation en URL canonique reconstruite à partir de l'identifiant de vidéo — jamais la chaîne brute de l'utilisateur |
| `acquisition/youtube.py` | Métadonnées (`fetch_metadata`) puis téléchargement/extraction audio (`download_audio`) via **l'API Python de yt-dlp**, jamais un appel système/shell |
| Limites appliquées | Durée max (`YOUTUBE_MAX_DURATION_SECONDS`, 15 min par défaut) vérifiée *avant* tout téléchargement, flux en direct refusés, taille bornée (`max_filesize` yt-dlp + réutilisation de `MAX_UPLOAD_SIZE_MB`), délai global (`YOUTUBE_DOWNLOAD_TIMEOUT_SECONDS`) |
| Réutilisation du pipeline de sécurité de l'Étape 4 | Le fichier téléchargé passe par `AudioFileStorage.save()` : détection de format par contenu réel, identifiant interne `uuid4`, aucun chemin construit à partir d'une donnée utilisateur |
| `POST /youtube-imports` | Nouvelle route, erreurs dédiées (`invalid_youtube_url` 400, `youtube_video_too_long` 422, `youtube_unavailable` 502, `youtube_timeout` 504) |
| `docs/API.md` | Section complète sur `/youtube-imports`, garanties de sécurité, limites honnêtes |
| Tests | 39 nouveaux tests, **entièrement simulés (mocks de `yt_dlp.YoutubeDL`), aucun accès réseau ni vidéo réelle** — backend à **94 tests au total** |

### Respect des consignes de conformité

- **Pas de contournement de restriction** : aucune option de cookies, d'authentification ou de contournement géographique n'est utilisée. Une vidéo privée/restreinte échoue normalement (`youtube_unavailable`).
- **Pas de commande système construite depuis une entrée utilisateur** : ce module n'utilise ni `subprocess` ni `os.system` nulle part — vérifié par un test dédié qui inspecte le code source du module pour s'en assurer.
- **URL toujours validée et reconstruite** avant d'atteindre `yt-dlp` : testé avec des tentatives d'URL malveillantes (hôte usurpé, identifiants dans l'URL, schéma `javascript:`, sous-domaine trompeur `youtube.com.evil.com`).

### Écart honnête à signaler

- Le délai maximal (`YOUTUBE_DOWNLOAD_TIMEOUT_SECONDS`) est appliqué via un thread Python avec timeout, pas via un sous-processus tuable. Cela borne proprement le temps d'attente **côté appelant** (l'API renvoie bien une erreur `504` à l'heure prévue), mais le thread `yt-dlp` sous-jacent peut en théorie continuer quelques secondes de plus en arrière-plan avant de s'arrêter de lui-même (borné par son propre `socket_timeout` interne de 30 s). Un vrai arrêt forcé nécessiterait de passer par un sous-processus dédié — non fait à ce stade pour rester sur l'API Python de yt-dlp (plus simple à tester, et qui évite toute question de construction de commande). À revisiter si ce comportement pose problème en usage réel.
- Comme à l'Étape 4, le nettoyage du répertoire temporaire (`data/tmp/youtube/`) est géré par un `finally` à chaque appel ; aucun nettoyage périodique automatique des résidus d'un arrêt brutal du processus n'est encore en place (utilitaire `_cleanup_stale_tmp_dirs` prévu mais non exposé).

### Résultats d'exécution réels

```
Backend : uv run pytest        → 94 passed
Backend : uv run ruff check .  → All checks passed!
Backend : uv run mypy backend/guitarriff → Success: no issues found in 24 source files
Frontend : npm run test        → 1 passed (inchangé)
```

## Historique — Étape 4 : gestion des fichiers audio locaux (30/09/2026)

> Statut : **import de fichiers audio locaux fonctionnel et sécurisé. Toujours aucune transcription.**

### Ce qui a été ajouté (par rapport à l'Étape 3)

| Élément | État |
|---|---|
| `acquisition/formats.py` | Détection du format réel par signature binaire (magic bytes) : WAV, FLAC, OGG, M4A, MP3 — jamais par extension ou `Content-Type` déclaré |
| `acquisition/storage.py` | Stockage sécurisé : identifiant interne `uuid4` généré côté serveur (seul composant de chemin), nom d'origine assaini conservé en métadonnée d'affichage uniquement, suppression contrôlée (`delete`), utilitaire `purge_all()` |
| `POST /audio-files` | Upload multipart, lecture par blocs de 1 Mo avec arrêt dès dépassement de `MAX_UPLOAD_SIZE_MB` (défaut 100 Mo) |
| `GET /audio-files/{id}` | Métadonnées du fichier importé |
| `DELETE /audio-files/{id}` | Suppression du fichier et de ses métadonnées |
| Erreurs dédiées (`errors.py`) | `UnsupportedFileTypeError` (415), `FileTooLargeError` (413), `InvalidFileIdError` (400) — toutes via l'enveloppe JSON cohérente de l'Étape 3 |
| `docs/API.md` | Section complète sur `/audio-files` et les garanties de sécurité de l'import |
| Tests | 38 nouveaux tests (détection de format, stockage, API) — **tous passent**, backend à **55 tests au total** |

### Vérifications de sécurité effectuées (réelles, pas supposées)

- Upload avec un nom de fichier `../../../etc/passwd.wav` : le fichier est stocké normalement sous son UUID, **aucun répertoire n'est créé en dehors de `data/uploads/`** (vérifié par test, y compris via l'API complète).
- Identifiants malformés (`..`, `/etc/passwd`, `not-a-uuid`, chaîne vide, forme encodée `%2e%2e%2f...`) : tous rejetés **avant** toute opération sur le système de fichiers (erreur `400 invalid_file_id`), jamais de 500.
- Contenu ne correspondant à aucun format audio (texte brut, en-tête d'exécutable ELF) : rejeté (`415`), y compris quand l'extension déclarée est `.wav`.
- Extension incohérente avec le contenu réel (ex. contenu WAV valide renommé `.mp3`) : rejeté (`415`).
- Test de bout en bout réel (pas seulement `TestClient`) : serveur `uvicorn` lancé, upload d'un vrai fichier WAV généré par FFmpeg via `curl`, cycle complet upload → consultation → suppression → 404 confirmé.

### Résultats d'exécution réels

```
Backend : uv run pytest        → 55 passed
Backend : uv run ruff check .  → All checks passed!
Backend : uv run mypy backend/guitarriff → Success: no issues found in 21 source files
```

### Écarts et points d'attention

- L'avertissement `httpx`/`TestClient` déjà signalé persiste, toujours sans impact.
- `purge_all()` existe mais n'est pas exposé via l'API ni planifié automatiquement — nettoyage manuel pour l'instant, à brancher sur une tâche planifiée quand la file de jobs (D6) sera implémentée.
- Toujours aucune transcription, aucun accès YouTube : conforme à la consigne de cette étape.

## Historique — Étape 3 : API et serveur minimal (29/09/2026)

> Statut : **socle API robuste en place (erreurs, config, CORS, doc). Toujours aucune fonctionnalité YouTube/transcription.**

### Ce qui a été ajouté (par rapport à l'Étape 2)

| Élément | État |
|---|---|
| Gestion d'erreurs centralisée (`errors.py`) | `AppError` + sous-classes (`NotFoundError`, `ValidationAppError`), handlers pour erreurs métier, validation Pydantic (422), routage (404/405) et erreurs internes non prévues (500) — **une seule enveloppe JSON cohérente** pour tous les cas |
| Sécurité des erreurs | Vérifié par test : aucune trace, aucun chemin système, aucun message d'exception brut ne fuite dans une réponse HTTP ; le détail complet est journalisé côté serveur uniquement |
| `GET /version` | Nouvelle route, renvoie nom + version du package |
| `GET /health` | Étendue avec un paramètre `verbose` (validé automatiquement par FastAPI) ajoutant des vérifications (ex. répertoire de données inscriptible) **sans jamais exposer de chemin absolu** |
| Configuration CORS | `CORS_ORIGINS` ajouté à `Settings` et `.env.example`, middleware CORS branché sur l'API, valeur par défaut alignée sur le port Vite (`http://localhost:5173`) |
| `docs/API.md` | Nouveau : routes disponibles, format des erreurs, garanties de sécurité, règles pour étendre l'API |
| Tests | 11 nouveaux tests (config CORS, `/version`, `/health?verbose`, 404/405/422/500, `AppError`) — **tous passent**, backend à **17 tests au total** |

### Résultats d'exécution réels

```
Backend : uv run pytest        → 17 passed
Backend : uv run ruff check .  → All checks passed!
Backend : uv run mypy backend/guitarriff → Success: no issues found in 18 source files
Frontend : npm run test        → 1 passed (inchangé, non touché à cette étape)
```

### Écarts et points d'attention

- L'avertissement `StarletteDeprecationWarning` sur `httpx`/`TestClient` (déjà noté à l'Étape 2) persiste — toujours sans impact, toujours non traité (upstream FastAPI/Starlette, pas notre code).
- Pas de route fonctionnelle au-delà de `/health` et `/version` : conforme à la consigne de ne pas démarrer le téléchargement YouTube ni la transcription à cette étape.
- Le frontend n'appelle toujours pas l'API (CORS est configuré et prêt, mais pas encore utilisé) — sera pertinent dès qu'une vraie interaction front/back sera développée.

## Historique — Étape 2 : fondations du projet (29/09/2026)

> Statut : **squelette d'application en place, testé et validé. Aucune fonctionnalité de transcription audio.**

### Décisions désormais actées (voir `TECHNICAL_DECISIONS.md` pour le détail)

- **Q1** : `yt-dlp` sera intégré (usage personnel, sous la responsabilité de l'utilisateur final).
- **Q2** : matériel cible non communiqué → valeurs par défaut prudentes retenues (concurrence de jobs = 1, Demucs différé).
- **Q3** : MVP limité à **guitare/basse** ; batterie et claviers hors périmètre V1 (voir `FEATURE_MATRIX.md`).

### Ce qui a été construit

| Élément | État |
|---|---|
| Arborescence backend (`backend/guitarriff/{acquisition,audio,separation,transcription,rhythm,model,tablature,midi,jobs,api}`) | Créée, modules vides (docstrings uniquement, conforme à la consigne de ne pas démarrer la fonctionnalité audio) |
| `pyproject.toml` | Dépendances backend fondation (FastAPI, Uvicorn, Pydantic/-settings) + extras dev (pytest, ruff, mypy) déclarées avec bornes de version reproductibles |
| `.python-version` | Épinglé sur `3.11` (décision D1) |
| Environnement Python | Installé via `uv sync --extra dev` — reproductible, testé |
| Configuration (`config.py`) | `Settings` typée (Pydantic Settings), lit `.env`/variables d'environnement, valeurs par défaut alignées sur D6 (concurrence=1) et Q1 (yt-dlp activable) |
| `.env.example` | Créé, sans secret, chaque variable commentée |
| Journalisation (`logging_config.py`) | Config `dictConfig` centralisée, niveau piloté par `Settings.log_level` |
| API FastAPI (`api/app.py`, `api/routes/health.py`) | Factory `create_app()` + route `/health` fonctionnelle, `lifespan` (pas l'API dépréciée `on_event`) |
| Frontend (`frontend/`) | Squelette Vite + React 19 + TypeScript généré, page de statut minimale (pas le boilerplate par défaut), testé |
| Tests backend | 6 tests (`config`, démarrage de l'app + `/health`) — **tous passent** |
| Tests frontend | 1 test de fumée (rendu du composant `App`) — **passe** |
| `.gitignore` | Couvre Python, Node, données de travail, `.env` |
| `README.md` | Commandes d'installation, configuration, lancement, tests, qualité |

### Résultats d'exécution réels (vérifiés dans ce même audit, pas supposés)

```
Backend : uv run pytest        → 6 passed
Backend : uv run ruff check .  → All checks passed!
Backend : uv run mypy backend/guitarriff → Success: no issues found in 16 source files
Frontend : npm run test        → 1 passed
Frontend : npm run build       → build réussi (dist/ généré)
Frontend : npm run lint (oxlint) → 0 warning, 0 erreur
```

### Écarts et points d'attention (honnêtes, pas cachés)

- Un avertissement de dépréciation subsiste dans les tests backend (`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2`). Il vient de Starlette/FastAPI eux-mêmes, pas du code du projet, n'affecte aucun test, et le paquet suggéré (`httpx2`) n'a pas été investigué plus avant à ce stade (pas nécessaire pour valider les fondations). À surveiller lors des prochaines mises à jour de FastAPI.
- Aucun `uv.lock` n'a encore été committé dans cette réponse — il est généré localement par `uv sync` et doit être ajouté au dépôt Git par toi lors du commit (voir section suivante).
- Le frontend n'est pas encore relié à l'API backend (aucun appel à `/health` depuis React) — hors périmètre de cette étape, qui portait sur les fondations de chaque côté séparément.

### Comment récupérer ce travail

Le dépôt distant `main` est vide ; je n'ai pas les droits d'écriture dessus (clone HTTPS anonyme). Le contenu complet a été livré sous forme de fichiers téléchargeables. Pour l'intégrer :

```bash
# Dans une copie locale du dépôt GuitarRiff
git add .
git commit -m "Étape 2 : fondations du projet (backend FastAPI + frontend Vite/React, config, tests)"
git push
```

Penser à committer `uv.lock` (généré par `uv sync`) pour figer les versions exactes installées.

## Historique — Étape 1 : audit (29/09/2026)

> Contenu conservé tel quel pour traçabilité ; les décisions Q1/Q2/Q3 mentionnées ci-dessous comme "ouvertes" sont désormais tranchées (voir section Étape 2 ci-dessus et `TECHNICAL_DECISIONS.md`).

## 1. État du dépôt

Le dépôt `Wildcode-Afk/GuitarRiff` a été cloné et inspecté intégralement (historique compris).

| Élément | Constat |
|---|---|
| Contenu actuel (branche `main`) | **Vide** — seul l'historique Git existe, aucun fichier de travail |
| Historique | 3 commits : `Initial commit` (ajout de `.gitattributes`), `initial` (ajout de `ARCHITECTURE.md` + `PROJECT_STATUS.md` — probablement issus d'une session précédente), `restart` (suppression de ces deux fichiers) |
| Branches distantes | `main`, `test` (contient uniquement `.gitattributes`) |
| Code frontend | Aucun |
| Code backend | Aucun |
| Fichiers de configuration | Aucun (`pyproject.toml`, `package.json`, `.gitignore`, CI, README absents) |
| Dépendances déclarées | Aucune |
| Tests | Aucun |

**Conclusion : projet greenfield.** Le "restart" a effacé la documentation précédente ; je n'ai pas repris son contenu tel quel — les constats ci-dessous ont été revérifiés indépendamment dans l'environnement d'audit.

## 2. Environnement d'audit (⚠️ mon bac à sable, pas ta machine cible)

Les vérifications ci-dessous ont été faites dans le conteneur où j'exécute ce travail, pas sur ton PC/serveur. À revalider sur l'environnement d'exécution réel avant de figer les choix.

| Outil | Version disponible |
|---|---|
| Python (système) | 3.12.3 |
| Node.js | 22.22.2 |
| npm | 10.9.7 |
| FFmpeg | 6.1.1 |
| uv (gestionnaire Python) | 0.11.7 disponible, permet d'installer d'autres versions de Python |
| Ressources machine (sandbox) | 1 cœur CPU, ~4 Go RAM — **contrainte forte pour tout traitement audio lourd (Demucs notamment)** |

## 3. Constat technique critique (vérifié, pas supposé)

**`basic-pitch` (backend TensorFlow) est incompatible avec Python 3.12.**

Vérification faite en conditions réelles (téléchargement des métadonnées PyPI + tentative d'installation, pas une simple lecture de doc) :

- `basic-pitch==0.4.0` déclare `tensorflow>=2.4.1,<2.15.1` comme dépendance sous Linux pour Python ≥ 3.11.
- Aucun wheel `tensorflow<2.15.1` n'existe pour Python 3.12 (le plus ancien disponible est `2.16.0rc0`). L'installation échoue donc telle quelle sous 3.12.
- **Sous Python 3.11**, `basic-pitch[tf]` s'installe correctement avec `tensorflow==2.15.0.post1`.
- Un second problème, indépendant de TensorFlow, a été découvert à l'exécution : la dépendance `resampy` importe `pkg_resources`, retiré des versions récentes de `setuptools` (≥ 81). Sans épingler `setuptools<81`, l'import de `basic_pitch.inference` échoue même sous Python 3.11. Avec `setuptools<81`, l'import fonctionne (vérifié : `basic_pitch.inference.predict` s'importe et le modèle ICASSP 2022 se charge).

**Décision qui en découle : le projet doit être développé et exécuté sous Python 3.11, avec `setuptools<81` épinglé.** Voir `TECHNICAL_DECISIONS.md`.

## 4. Autre dépendance vérifiée : Demucs

- `demucs==4.1.0` déclare `Requires-Python: >=3.10` et `torch>=2.1` — donc compatible avec le même environnement Python 3.11 que `basic-pitch`.
- Je n'ai pas installé `torch`+`demucs` en entier dans ce bac à sable (téléchargement de plusieurs Go, non nécessaire pour valider la compatibilité de version). À tester en conditions réelles à l'étape d'implémentation.
- **Risque de performance non résolu** : Demucs (séparation de sources) est coûteux en CPU/RAM. Sur une machine à 1 cœur / 4 Go de RAM (le bac à sable), il est probable qu'un traitement complet soit très lent ou échoue par manque de mémoire. Ceci doit être testé sur le matériel cible réel (pas supposé).

## 5. Problèmes détectés (résumé)

1. Le dépôt est totalement vide — tout est à construire depuis zéro.
2. Contrainte de version Python stricte (3.11 uniquement) à cause de `basic-pitch[tf]`.
3. Dépendance transitive cassée (`resampy` → `pkg_resources`) nécessitant un pin explicite de `setuptools`.
4. Aucune information sur le matériel cible réel (RAM/CPU/OS de la machine où l'app tournera) — condition les choix sur Demucs et sur l'exécution locale vs différée.
5. Question ouverte, non tranchée par toi dans ce prompt : **comment récupérer l'audio depuis un lien YouTube ?** (`yt-dlp` est l'outil de facto, mais son usage soulève des questions de conditions d'utilisation de YouTube à trancher — voir `TECHNICAL_DECISIONS.md`, Q1).

## 6. Prochaine étape proposée

Voir le plan de développement dans le rapport final (fin de réponse). **Aucun développement ne démarre avant ta validation explicite.**
