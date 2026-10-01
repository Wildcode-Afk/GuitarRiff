# GuitarRiff — API

> Statut : **socle API (Étape 3)**. Aucune route de téléchargement YouTube ni
> de transcription audio n'est encore exposée.

## Base URL

En développement : `http://127.0.0.1:8000` (voir `API_HOST`/`API_PORT` dans
`.env`). Pas de préfixe de version (`/v1/...`) à ce stade — à introduire si
l'API devient publique.

## Documentation interactive

FastAPI génère automatiquement :
- Swagger UI : `GET /docs`
- OpenAPI JSON : `GET /openapi.json`

## Routes disponibles

### `GET /health`

Vérifie que l'application tourne et que la configuration est chargée.

Paramètre de requête optionnel :

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `verbose` | `bool` | `false` | Ajoute des vérifications supplémentaires (voir ci-dessous) |

Réponse (`200`) :

```json
{
  "status": "ok",
  "app_env": "development",
  "job_concurrency": 1,
  "ytdlp_enabled": true
}
```

Avec `?verbose=true`, un champ `checks` est ajouté :

```json
{
  "...": "...",
  "checks": {
    "data_dir_writable": true
  }
}
```

**Sécurité :** `checks` ne contient que des indicateurs booléens, jamais un
chemin de fichier ou une valeur de configuration sensible.

### `GET /version`

Réponse (`200`) :

```json
{ "name": "guitarriff", "version": "0.1.0" }
```

### `POST /audio-files`

Importe un fichier audio local (multipart/form-data, champ `file`). Ne
déclenche aucune transcription — stocke uniquement le fichier et renvoie ses
métadonnées.

**Formats acceptés** (vérifiés sur le contenu binaire réel du fichier, pas sur
l'extension ni le `Content-Type` déclaré par le client — voir « Sécurité »
ci-dessous) : WAV, FLAC, OGG (Vorbis/Opus), M4A/AAC, MP3.

**Taille maximale** : `MAX_UPLOAD_SIZE_MB` (100 Mo par défaut, voir `.env.example`).

Réponse (`201`) :

```json
{
  "file_id": "684754d3-cd53-44d7-8cfd-c3ac4fcfbb5b",
  "original_filename": "ma_chanson.wav",
  "format": "wav",
  "content_type": "audio/wav",
  "size_bytes": 88278,
  "uploaded_at": "2026-09-30T18:07:19.895120+00:00",
  "status": "stored"
}
```

Erreurs possibles : `415` (`unsupported_file_type` — format non reconnu ou
extension incohérente avec le contenu), `413` (`file_too_large`).

### `GET /audio-files/{file_id}`

Renvoie les métadonnées d'un fichier déjà importé (même forme que la réponse
de `POST /audio-files`). `404` (`not_found`) si l'identifiant est inconnu,
`400` (`invalid_file_id`) s'il n'a pas la forme d'un UUID.

### `DELETE /audio-files/{file_id}`

Supprime le fichier et ses métadonnées. `204` en cas de succès, `404`
(`not_found`) si l'identifiant est inconnu.

### Sécurité de l'import de fichiers

- **L'extension déclarée et le `Content-Type` du client ne sont jamais
  fiables** : le format est déterminé en lisant la signature binaire
  (« magic bytes ») du fichier lui-même (voir
  `backend/guitarriff/acquisition/formats.py`). Une extension incohérente
  avec le contenu détecté est rejetée.
- **Aucune traversée de répertoire possible** : chaque fichier reçoit un
  identifiant interne (`uuid4`) généré côté serveur, qui est le seul élément
  utilisé pour construire le chemin de stockage. Le nom de fichier d'origine
  fourni par le client n'est conservé que comme métadonnée d'affichage
  (assaini), jamais comme composant de chemin — voir
  `backend/guitarriff/acquisition/storage.py`.
- **Taille bornée dès la lecture** : le contenu est lu par blocs de 1 Mo ;
  l'import est interrompu dès que la limite configurée est dépassée, sans
  attendre d'avoir reçu tout le fichier.
- Un utilitaire `AudioFileStorage.purge_all()` existe pour vider le
  répertoire d'upload (nettoyage manuel ou tâche planifiée à ajouter plus
  tard) — non exposé via l'API à ce stade.

### `POST /youtube-imports`

Importe l'audio d'une vidéo YouTube. **Usage strictement personnel, sous la
responsabilité de l'utilisateur final** (décision Q1, voir
`docs/TECHNICAL_DECISIONS.md`) — ne contourne aucune restriction d'accès
(pas de cookies, pas d'authentification, pas de contournement géographique).

Corps de la requête :

```json
{ "url": "https://www.youtube.com/watch?v=XXXXXXXXXXX" }
```

**URL acceptées** : `youtube.com`, `www.youtube.com`, `m.youtube.com`,
`music.youtube.com`, `youtu.be` — sous forme `/watch?v=`, `/shorts/`,
`/embed/`, `/live/`, ou lien court `youtu.be/<id>`. Toute autre URL est
rejetée. L'URL réellement utilisée pour l'extraction est **toujours
reconstruite** à partir de l'identifiant de vidéo validé, jamais la chaîne
fournie telle quelle.

**Limites appliquées avant tout téléchargement** :
- Durée maximale : `YOUTUBE_MAX_DURATION_SECONDS` (15 min par défaut) —
  vérifiée à partir des métadonnées, avant de télécharger quoi que ce soit.
- Flux en direct (durée indéterminée) : refusés.
- Taille du fichier téléchargé : bornée par `MAX_UPLOAD_SIZE_MB` (même
  limite que l'import de fichier local).
- Temps total de l'opération : `YOUTUBE_DOWNLOAD_TIMEOUT_SECONDS` (120 s par
  défaut).

Réponse (`201`) — même forme que `POST /audio-files`, avec les champs de
provenance renseignés :

```json
{
  "file_id": "...",
  "original_filename": "dQw4w9WgXcQ.wav",
  "format": "wav",
  "content_type": "audio/wav",
  "size_bytes": 4823110,
  "uploaded_at": "...",
  "status": "stored",
  "source": "youtube",
  "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "title": "Titre de la vidéo"
}
```

Erreurs possibles :

| Cas | Code HTTP | `error.code` |
|---|---|---|
| URL non reconnue comme une URL YouTube valide | 400 | `invalid_youtube_url` |
| Vidéo trop longue, ou flux en direct | 422 | `youtube_video_too_long` |
| Vidéo indisponible, privée, ou échec d'extraction/téléchargement | 502 | `youtube_unavailable` |
| Délai maximal dépassé | 504 | `youtube_timeout` |
| Fichier résultant trop volumineux | 413 | `file_too_large` |

### Sécurité et limites de l'acquisition YouTube

- **Aucune commande système n'est construite à partir d'une entrée
  utilisateur** : ce module utilise exclusivement l'API Python de `yt-dlp`
  (`import yt_dlp`), jamais un appel `subprocess`/shell — il n'existe donc
  aucune chaîne de commande dans laquelle une URL pourrait s'injecter.
- **Aucun contournement de restriction** : pas de cookies, pas
  d'authentification, pas de contournement géographique. Une vidéo privée,
  restreinte par l'âge ou indisponible échoue normalement (`youtube_unavailable`)
  plutôt que d'être contournée.
- Le fichier téléchargé passe par **le même pipeline de sécurité que
  l'upload local** (Étape 4) : détection de format par contenu réel,
  identifiant interne `uuid4`, aucun chemin construit à partir d'une donnée
  utilisateur (titre de vidéo, nom de fichier).
- **Limite de temps honnête** : le délai configuré borne le temps d'attente
  côté appelant (l'API répond en `504` au-delà). Comme l'extraction passe
  par un thread plutôt qu'un sous-processus, ce thread peut en théorie
  continuer quelques instants en arrière-plan après le signalement du
  timeout côté client — borné en pratique par le `socket_timeout` interne
  de `yt-dlp` (30 s). Voir `docs/PROJECT_STATUS.md` pour le détail de cet
  arbitrage.

## Format des erreurs

Toutes les erreurs (validation, route inconnue, méthode non autorisée,
erreurs métier, erreurs internes) renvoient la même enveloppe JSON :

```json
{
  "error": {
    "code": "validation_error",
    "message": "Les données envoyées sont invalides.",
    "details": {}
  }
}
```

| Cas | Code HTTP | `error.code` |
|---|---|---|
| Route inexistante | 404 | `http_404` |
| Méthode non autorisée | 405 | `http_405` |
| Paramètre/entrée invalide (schéma Pydantic) | 422 | `validation_error` |
| Ressource introuvable (ex. fichier audio inconnu) | 404 | `not_found` |
| Identifiant de fichier malformé (pas un UUID) | 400 | `invalid_file_id` |
| Format de fichier non supporté ou incohérent | 415 | `unsupported_file_type` |
| Fichier trop volumineux | 413 | `file_too_large` |
| Erreur interne non prévue | 500 | `internal_error` |

### Garanties de sécurité

- **Aucun chemin système, trace d'exécution ou message d'exception brut
  n'est jamais renvoyé au client.** Les erreurs non prévues sont
  journalisées en détail côté serveur (`logger.exception`) mais la réponse
  HTTP reste toujours le message générique `"Une erreur interne est
  survenue."`.
- Les erreurs de validation (422) ne remontent que `loc` (chemin du champ),
  `msg` et `type` — jamais d'objet interne de Pydantic.

## CORS

Les origines autorisées à appeler l'API (pour le frontend) sont configurées
via `CORS_ORIGINS` dans `.env` (liste séparée par des virgules). Par défaut :
`http://localhost:5173` (port par défaut de Vite en développement).

## Étendre l'API (pour les prochaines étapes)

- Toute nouvelle route doit utiliser `guitarriff.errors.AppError` (ou une
  sous-classe) pour ses erreurs métier plutôt que de lever des exceptions
  génériques ou de construire des réponses d'erreur ad hoc.
- Toute donnée d'entrée doit passer par un modèle Pydantic (validation
  automatique, erreurs 422 cohérentes).
- Ne jamais inclure un chemin absolu du système de fichiers dans une
  réponse HTTP (voir `/health?verbose=true` pour l'exemple à suivre :
  indicateur booléen plutôt que valeur brute).
