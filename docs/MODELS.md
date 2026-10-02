# GuitarRiff — Modèles de séparation d'instruments

> Concerne la fonctionnalité de séparation (Étape 7). Pour la transcription
> (`basic-pitch`), voir `docs/ARCHITECTURE.md` et `docs/TECHNICAL_DECISIONS.md`.

## Vue d'ensemble

GuitarRiff utilise **Demucs** (Meta AI / Alexandre Défossez) pour séparer un
mélange audio en pistes approximatives (batterie, basse, autres, voix — et
en option guitare/piano). C'est une **dépendance optionnelle** : l'absence
de Demucs est une situation normale et gérée proprement par l'application
(mode `none`, pas de séparation), pas une erreur de configuration.

## Installation

Demucs **n'est pas installé par défaut** (`uv sync --extra dev` ne
l'installe pas). Pour l'activer :

```bash
# 1. Installer torch en CPU-only d'abord (voir avertissement ci-dessous)
uv pip install torch --index-url https://download.pytorch.org/whl/cpu

# 2. Puis l'extra "separation" du projet
uv sync --extra separation
```

### ⚠️ Avertissement important, vérifié dans cet environnement

**Ne faites pas simplement `pip install demucs` ou `pip install torch` sans
préciser l'index CPU.** Nous avons vérifié par une résolution de dépendances
réelle (pas une supposition) que l'installation par défaut de `torch` depuis
PyPI entraîne toute la pile CUDA, même sans GPU :

```
+ nvidia-cublas==13.1.1.3
+ nvidia-cuda-cupti==13.0.85
+ nvidia-cuda-nvrtc==13.0.88
+ nvidia-cuda-runtime==13.0.96
+ nvidia-cudnn-cu13==9.24.0.43
+ nvidia-cufft==12.0.0.61
+ nvidia-cufile==1.15.1.6
+ nvidia-curand==10.4.0.35
+ nvidia-cusolver==12.0.4.66
+ nvidia-cusparse==12.6.3.3
+ nvidia-cusparselt-cu13==0.8.1
+ nvidia-nccl-cu13==2.30.7
+ nvidia-nvjitlink==13.4.92
+ nvidia-nvshmem-cu13==3.4.5
+ nvidia-nvtx==13.0.85
+ torch==2.14.1
+ triton==3.8.0
```

Plusieurs gigaoctets de paquets CUDA totalement inutiles en mode CPU. Passer
par l'index dédié (`https://download.pytorch.org/whl/cpu`) installe une
version de `torch` sans ces dépendances. **C'est le mode d'installation
recommandé pour GuitarRiff**, qui cible explicitement le CPU à ce stade (voir
ci-dessous).

### Ce qui n'a pas pu être vérifié dans ce bac à sable

Le réseau de l'environnement de développement utilisé pour écrire ce code
n'a pas accès à `download.pytorch.org` (uniquement PyPI), et l'espace disque
disponible (~7 Go) ne permettait pas d'installer la pile CUDA complète pour
tester. **L'intégration Demucs (`separation/engine.py`) suit le schéma
documenté par l'API Python officielle de Demucs, mais n'a pas pu être
exécutée contre une vraie installation torch+demucs dans cet environnement.**
Elle est entièrement couverte par des tests avec simulation (voir
`backend/tests/unit/test_separation_engine.py`), mais **doit être validée
avec une installation réelle avant toute mise en production.**

## Mode CPU

Cette étape cible explicitement l'exécution CPU :
- `separation/engine.py` appelle Demucs avec `device="cpu"` en dur, sans
  détection ni usage de GPU à ce stade.
- `separation/capabilities.py` détecte néanmoins la disponibilité de CUDA
  (`torch.cuda.is_available()`) de façon informative (exposée dans
  `GET /health?verbose=true`), en vue d'une itération future qui
  l'exploiterait réellement.
- Une vérification de mémoire disponible (`SEPARATION_MIN_AVAILABLE_MEMORY_MB`,
  1500 Mo par défaut) précède tout lancement — voir `docs/API.md`.

## Modèles disponibles

| Mode | Pistes | Statut | Limites connues |
|---|---|---|---|
| `none` | `mixture` | Stable | Pas de séparation — passe l'audio tel quel |
| `htdemucs` | drums, bass, other, vocals | Stable (modèle standard Demucs v4) | `other` contient la guitare mélangée avec claviers/synthés — **pas une guitare isolée** |
| `htdemucs_6s` | + guitar, piano | **Expérimental** (qualifié ainsi par Demucs lui-même) | Guitare : qualité correcte mais non parfaite. Piano : beaucoup de bruit de fond et d'artefacts, d'après la documentation amont |

**Aucun mode ne produit des instruments parfaitement isolés.** Artefacts et
fuites entre pistes sont systématiques. L'API répercute ces limites dans le
champ `notes` de chaque réponse (voir `docs/API.md`) — ne jamais les retirer
de l'interface utilisateur finale.

## Téléchargement des modèles et cache

Demucs télécharge automatiquement les poids pré-entraînés au premier usage
d'un modèle donné (comportement standard de la bibliothèque). Le réglage
`SEPARATION_ALLOW_MODEL_DOWNLOAD` (true par défaut) peut désactiver ce
téléchargement automatique.

**Limitation assumée** : nous n'avons pas pu vérifier de façon fiable, dans
cet environnement, l'emplacement exact du cache local des modèles
pré-entraînés de Demucs (pour implémenter une détection "déjà en cache" avant
de refuser un téléchargement). En conséquence, quand
`SEPARATION_ALLOW_MODEL_DOWNLOAD=false`, le chargement du modèle est
simplement refusé (`separation_model_unavailable`), que le modèle soit déjà
présent localement ou non. Une détection plus fine est possible mais devra
être vérifiée contre une vraie installation de Demucs — voir l'avertissement
ci-dessus.

## Licences — à lire avant tout usage au-delà du personnel

**Le code de Demucs est MIT.** Vérifié via plusieurs sources indépendantes
(classifieur PyPI, `setup.py` du dépôt officiel `facebookresearch/demucs`,
paquets de distribution tiers). Ceci ne pose aucune question pour
GuitarRiff, qui est lui-même un projet libre et open source.

**La licence des POIDS pré-entraînés (les modèles eux-mêmes, pas le code)
est moins claire et a fait l'objet de questions répétées, non définitivement
tranchées publiquement à notre connaissance :**

- L'auteur de Demucs (Alexandre Défossez) aurait indiqué dans plusieurs
  discussions GitHub (citées dans des échanges publics sur Hugging Face) que
  les poids pré-entraînés ne sont pas couverts par la licence MIT du code et
  sont *« fournis à des fins de recherche »*, en raison des conditions
  d'utilisation du jeu de données d'entraînement MusDB.
- Des utilisateurs ont par la suite remarqué des incohérences dans les
  métadonnées de licence affichées sur certaines pages de modèles
  (mentionnant parfois "MIT" directement sur la fiche du modèle), et ont posé
  la question directement à l'auteur sans qu'une réponse publique définitive
  n'ait pu être confirmée au moment de la rédaction de ce document.

**Nous ne sommes pas en mesure de trancher cette question à la place de
l'utilisateur — ce n'est pas un avis juridique.** Ce que nous pouvons dire :

- L'usage prévu par GuitarRiff à ce stade — téléchargement des poids par
  l'utilisateur final sur sa propre machine, exécution locale, pour un usage
  personnel de pratique musicale, sans redistribution des poids ni des
  pistes séparées — correspond au mode d'usage le plus courant et le moins
  disputé de Demucs par la communauté.
- Si GuitarRiff devait un jour être distribué commercialement, embarquer les
  poids directement dans un produit payant, ou redistribuer des pistes
  séparées publiquement, cette question de licence devrait être
  **re-vérifiée sérieusement avant toute décision**, idéalement en
  contactant directement les auteurs de Demucs.

## Résumé des réglages (voir aussi `.env.example`)

| Variable | Défaut | Rôle |
|---|---|---|
| `SEPARATION_MIN_AVAILABLE_MEMORY_MB` | 1500 | Mémoire dispo minimale pour démarrer une séparation |
| `SEPARATION_TIMEOUT_SECONDS` | 900 | Délai avant qu'une séparation en cours soit signalée en timeout |
| `SEPARATION_ALLOW_MODEL_DOWNLOAD` | true | Autorise Demucs à télécharger un modèle non encore en cache |

Ces limites réutilisent par ailleurs `AUDIO_MAX_DURATION_SECONDS` (Étape 6)
pour la durée maximale de l'audio traité.
