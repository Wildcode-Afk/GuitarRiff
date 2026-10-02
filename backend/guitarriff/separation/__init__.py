"""Séparation d'instruments (Demucs, dépendance optionnelle — voir
docs/MODELS.md).

`capabilities.py` : détection CPU/mémoire/torch/demucs disponibles.
`models.py` : modes de séparation disponibles et leurs limites connues.
`progress.py` : suivi de progression en mémoire (process unique).
`engine.py` : seul point d'import de `torch`/`demucs`.
`service.py` : orchestration (cache, mémoire, durée, exécution en arrière-plan).

Aucune séparation n'est garantie parfaite — voir `models.py` pour le détail
des limites de chaque mode, à répercuter dans toute réponse API.
"""
