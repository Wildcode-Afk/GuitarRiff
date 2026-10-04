"""Transcription de notes via basic-pitch (Spotify) — Étape 9.

`basic_pitch_adapter.py` : seul point d'import de `basic_pitch` (isolation,
voir docs/ARCHITECTURE.md principe 2) ; vérifié par une installation et une
inférence réelles (pas une supposition), voir le docstring de ce module.
`converter.py` : conversion pure des notes brutes vers `NoteEvent`.
`service.py` : orchestration (résolution de la source, mise à jour du Song
persisté, préférence pour les pistes séparées quand pertinent).

basic-pitch ne reconnaît jamais parfaitement un instrument dans un mélange
complet — voir le disclaimer toujours renvoyé par `service.transcribe`, à
répercuter dans toute interface utilisateur exposant un résultat.
"""
