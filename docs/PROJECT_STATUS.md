# GuitarRiff — État du projet

## Étape 2 — Fondations du projet (terminée le 29/09/2026)

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
