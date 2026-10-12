"""Mapping des notes transcrites vers le manche (corde/case) — Étape 11.

`fretboard.py` : configuration (accordage, capodastre, limite de cases) et
génération des positions candidates pour une hauteur MIDI donnée.
`cost.py` : fonction de coût (déplacement, écart entre doigts, jouabilité) —
heuristique documentée, pas une reconstitution du doigté réel du guitariste.
`mapper.py` : groupement des notes simultanées, résolution combinatoire,
signalement explicite des notes impossibles à placer.
`service.py` : orchestration sur le `Song` persisté (Étape 9).
"""
