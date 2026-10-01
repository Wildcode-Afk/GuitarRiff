"""Normalisation audio.

`ffmpeg.py` : lecture de métadonnées (`ffprobe`) et conversion (`ffmpeg`) vers
le format interne cible (22050 Hz, mono, PCM 16 bits — justifié par les
besoins de `basic-pitch`, voir le docstring de ce module).
`service.py` : orchestration (durée max, stockage du résultat normalisé).
"""
