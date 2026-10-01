# GuitarRiff — État du projet

## Étape 5 — Acquisition depuis YouTube (terminée le 30/09/2026)

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
