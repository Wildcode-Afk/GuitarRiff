"""Analyse rythmique (tempo, battements, métrique) — Étape 10.

`analyzer.py` : seul point d'import direct de `librosa` ; détection de
tempo/battements/changements de tempo avec une vraie mesure de confiance.
Ne détecte jamais la métrique (aucune bibliothèque fiable retenue pour
cela — voir le docstring de ce module et docs/TECHNICAL_DECISIONS.md).
`service.py` : orchestration, mise à jour du `Song` persisté, distinction
explicite détecté (`EstimationSource.DETECTED`) / manuel (`MANUAL`).
"""
