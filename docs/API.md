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
| Erreur métier (ex. ressource introuvable) | variable (ex. 404) | ex. `not_found` |
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
