"""Analyse harmonique (Étape 13) : accords et piste clavier.

`templates.py` : modèles d'accords et classement par similarité (pur).
`analyzer.py` : estimation d'accords à partir de l'audio — base de référence
(chroma `librosa` + décomposition en notes), pas un modèle entraîné.
`from_notes.py` : déduction d'accords à partir de notes transcrites.
`keyboard.py` : piste clavier simple à partir d'accords.
`service.py` : orchestration sur le `Song` persisté.

Deux fonctionnalités distinctes : *obtenir* des accords (estimés, déduits ou
corrigés par l'utilisateur) et *générer* une représentation jouable à partir
d'eux. Un accord ambigu n'est jamais présenté comme certain.
"""
