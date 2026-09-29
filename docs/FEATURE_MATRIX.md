# GuitarRiff — Matrice des fonctionnalités

> Classement basé sur l'audit technique réel (dépendances testées), pas sur des suppositions.
> Légende : **MVP** = nécessaire à une première version utilisable · **V2** = utile mais différable · **Expérimental** = faisabilité ou précision incertaine, à traiter comme un prototype séparé.

| # | Fonctionnalité | Classement | Justification |
|---|---|---|---|
| 1 | Import d'un fichier audio local | **MVP** | Aucune dépendance externe risquée, aucune question légale. Base la plus sûre pour démarrer. |
| 2 | Acquisition depuis une URL YouTube | **V2** | Décision Q1 (29/09/2026) : retenue via `yt-dlp`, usage personnel sous la responsabilité de l'utilisateur final. Reste classée V2 : l'import de fichier local (MVP) doit être solide en premier, `yt-dlp` s'ajoute derrière la même interface d'acquisition sans bloquer le MVP. |
| 3 | Normalisation audio (FFmpeg) | **MVP** | Brique déjà disponible et fiable dans l'environnement testé (FFmpeg 6.1.1 présent). |
| 4 | Séparation d'instruments (Demucs) | **V2** | Compatible en version de dépendances avec l'environnement Python 3.11 retenu, mais coût CPU/RAM non validé sur le matériel cible. Le MVP peut fonctionner sur un fichier déjà mono-instrument (ex. DI guitare) sans séparation. |
| 5 | Transcription des notes (guitare/basse) via `basic-pitch` | **MVP** | Seule brique de transcription open source mature identifiée. Fonctionne, mais avec des limites de précision réelles sur audio polyphonique dense (accords, distorsion) — à communiquer clairement à l'utilisateur, pas à présenter comme parfait. |
| 6 | Détection tempo / mesures / rythme (`librosa`) | **MVP** | `librosa` est fiable pour cette tâche précise (ce n'est pas un rôle de transcription de notes, donc pas soumis aux mêmes limites). |
| 7 | Génération de tablature guitare/basse | **MVP** | Dépend uniquement de `NoteEvent`, pas d'une bibliothèque tierce lourde. Cœur de la proposition de valeur du projet. |
| 8 | Transcription batterie | **Hors périmètre V1** *(décision Q3, 29/09/2026)* | Aucune bibliothèque open source équivalente à `basic-pitch` identifiée pour la batterie avec un niveau de fiabilité comparable. Exclu explicitement du MVP, à réévaluer après la V1. |
| 9 | Transcription claviers/piano | **Hors périmètre V1** *(décision Q3, 29/09/2026)* | `basic-pitch` gère le piano correctement en mono-instrument, mais l'extraire proprement d'un mix nécessite Demucs en amont. Exclu explicitement du MVP au même titre que la batterie. |
| 10 | Modèle musical commun (multi-pistes) | **MVP** | Nécessaire dès qu'il y a plus d'une piste transcrite ; structure de données, pas de dépendance externe. |
| 11 | Éditeur web (lecture + édition manuelle) | **MVP (version simple)** | Une édition basique (corriger une note, un silence) est nécessaire vu les limites de précision du point 5. Édition avancée (styles, techniques de jeu) en V2. |
| 12 | Export MIDI | **MVP** | `pretty_midi` est déjà une dépendance de `basic-pitch`, coût d'implémentation faible. |
| 13 | Export PDF (partition/tab imprimable) | **V2** | Utile mais indépendant du cœur pipeline ; peut s'appuyer sur le rendu SVG déjà utilisé à l'écran. |
| 14 | Exécution locale complète (sans service cloud) | **MVP (objectif produit)** | Conforme à l'esprit "gratuit et open source" du projet, mais dépend directement des résultats de test réels sur Demucs (risque de lenteur/mémoire, voir `PROJECT_STATUS.md`). |

## Précisions sur les limites de précision (à ne pas présenter comme résolues)

- La transcription automatique d'audio polyphonique (accords plaqués, guitare saturée) est un problème de recherche actif : `basic-pitch` donne de bons résultats sur du monophonique/peu polyphonique propre, mais des résultats dégradés sur un mix dense ou très distordu. Le produit doit communiquer un niveau de confiance, pas une garantie d'exactitude.
- La séparation de sources (Demucs) introduit elle-même des artefacts qui peuvent dégrader la transcription en aval — l'enchaînement séparation → transcription n'est pas neutre et doit être évalué avec de vrais fichiers avant d'être promis à l'utilisateur.
