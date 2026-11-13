# GuitarRiff — Décisions techniques

> **Statut des questions ouvertes (validé le 29/09/2026) :**
> - **Q1** — Acquisition YouTube : **retenu** — intégrer `yt-dlp`, usage personnel, sous la responsabilité de l'utilisateur final, encapsulé derrière une interface remplaçable.
> - **Q2** — Matériel cible : non communiqué — on garde les valeurs par défaut prudentes (concurrence de jobs = 1, Demucs différé tant que non testé en charge réelle).
> - **Q3** — Portée V1 : **MVP limité à guitare/basse.** Batterie et claviers restent hors périmètre de la V1 (voir `FEATURE_MATRIX.md`).

> Chaque décision ci-dessous est appuyée sur une vérification faite pendant l'audit (installation réelle, lecture de métadonnées PyPI), pas sur une supposition. Les questions ouvertes sont listées séparément et attendent ta validation.

## D1 — Le projet cible Python 3.11, pas 3.12

**Constat vérifié :**
- `basic-pitch==0.4.0` exige `tensorflow>=2.4.1,<2.15.1` sous Linux pour Python ≥ 3.11.
- Aucun wheel TensorFlow `<2.15.1` n'existe pour Python 3.12 (le plus ancien wheel disponible pour 3.12 est `2.16.0rc0`) : l'installation échoue telle quelle.
- Sous Python 3.11, `basic-pitch[tf]` s'installe et se charge correctement avec `tensorflow==2.15.0.post1` (testé).

**Décision :** épingler le projet sur Python 3.11 via `uv` (`.python-version` + `requires-python = ">=3.11,<3.12"`).

**Alternative non retenue pour l'instant :** le backend ONNX de `basic-pitch` (`onnxruntime`), qui pourrait potentiellement fonctionner sous 3.12. Non testé pendant cet audit — à évaluer seulement si la contrainte Python 3.11 devient bloquante (ex. dépendance future incompatible).

## D2 — Épingler `setuptools<81`

**Constat vérifié :** même sous Python 3.11, l'import de `basic_pitch.inference` échoue avec `ModuleNotFoundError: No module named 'pkg_resources'`. En cause : la dépendance transitive `resampy` importe encore `pkg_resources`, retiré des versions récentes de `setuptools`. Avec `setuptools==80.10.2` (< 81), l'import fonctionne (avec un simple avertissement de dépréciation, pas une erreur).

**Décision :** épingler explicitement `setuptools<81` dans les dépendances du projet tant que `resampy` n'a pas corrigé cet import en amont. À réévaluer périodiquement (vérifier les releases de `resampy`).

## D3 — `basic-pitch` isolé derrière une interface `Transcriber`

**Raison :** c'est une dépendance lourde (TensorFlow), avec des contraintes de version fragiles (voir D1, D2) qui peuvent évoluer indépendamment du reste du projet. L'isoler dans un seul module permet de la remplacer (ONNX, autre modèle) sans toucher au reste du code.

## D4 — `librosa` n'est pas un substitut à `basic-pitch`

**Raison :** `librosa` est une bibliothèque d'analyse de signal (tempo, beats, séparation harmonique/percussive, features spectrales) — elle ne fait pas de transcription polyphonique de notes. La confusion entre les deux rôles est une erreur fréquente dans ce type de projet ; ce document la tranche explicitement pour éviter qu'elle ne s'installe dans le code plus tard.

## D5 — Demucs retenu en dépendance de version, mais non validé en charge réelle

**Constat vérifié :** `demucs==4.1.0` déclare `Requires-Python: >=3.10` et `torch>=2.1` — compatible avec l'environnement Python 3.11 choisi en D1.

**Non vérifié pendant cet audit :** le temps de traitement et la consommation mémoire réels de Demucs sur le matériel cible. Le bac à sable de cet audit (1 cœur CPU, ~4 Go RAM) n'est probablement pas représentatif de ta machine réelle, donc je n'ai pas tiré de conclusion à partir de là — cela reste à tester en conditions réelles avant de décider si Demucs fait partie du MVP ou d'une V2 (voir `FEATURE_MATRIX.md`).

## D6 — File d'attente de jobs à concurrence 1

**Raison :** TensorFlow (via `basic-pitch`) et potentiellement Demucs/PyTorch ont une empreinte mémoire significative. Sur une machine modeste, exécuter deux jobs en parallèle risque l'épuisement mémoire plutôt qu'un gain de débit. Concurrence = 1 par défaut, ajustable une fois le matériel cible connu.

## D7 — Frontend Vite + React + TypeScript

**Raison :** choix par défaut proposé faute de contrainte exprimée dans ce prompt ; cohérent avec un projet web moderne consommant une API typée. Ce choix n'a pas d'impact sur le contrat backend (`NoteEvent`) et peut être reconsidéré sans coût architectural.

## D8 — `librosa` pour le tempo/battements, aucune détection de métrique (Étape 10)

**Constat vérifié :** `librosa` (déjà une dépendance transitive de
`basic-pitch`, aucun coût d'ajout) fournit une détection de tempo/battements
robuste (`librosa.beat.beat_track`) mais **aucun détecteur de métrique
fiable** intégré.

**Bibliothèque alternative étudiée et écartée : `madmom`.** C'est la
référence historique pour le suivi de "downbeat"/métrique, mais le paquet
PyPI officiel (`CPJKU/madmom`) n'est plus maintenu depuis plusieurs années et
s'installe difficilement sur des versions récentes de Python/NumPy (extensions
Cython compilées, constat indépendant). Une réimplémentation plus récente
(`madmom-infer`, 2026, pur NumPy/SciPy) existe et a été notée, mais reste un
projet jeune et spécialisé ; son ajout n'a pas été jugé justifié pour cette
étape.

**Décision :** `librosa` pour tempo/battements/changements de tempo, avec une
mesure de confiance dérivée de la cohérence du tempo local sur la durée du
morceau (vérifiée empiriquement : ~1.0 sur un signal rythmique régulier, ~0.23
sur du bruit blanc sans rythme). **Aucune détection de métrique** : une
métrique par défaut (4/4) non confirmée (`confidence=None`) est appliquée tant
que l'utilisateur ne la corrige pas manuellement — conformément à la consigne
de ne pas déduire une métrique certaine d'une estimation incertaine. À
revisiter si `madmom-infer` (ou un équivalent) gagne en maturité et qu'un
besoin réel de détection de métrique se confirme.

## D9 — Estimation d'accords : base `librosa` sans modèle entraîné (Étape 13)

**Question posée :** la reconnaissance fiable d'accords nécessite-t-elle une
bibliothèque supplémentaire ? Si oui, laquelle, et pourquoi ?

**Options étudiées (métadonnées PyPI et dépendances lues, pas supposées) :**

| Option | Constat vérifié | Verdict |
|---|---|---|
| `crema` | ISC ; dernière release avril 2022 ; exige `tensorflow`, `keras`, `pumpp`, `jams` | Écartée : ancienne, lourde |
| `autochord` | MIT ; dernière release octobre 2021 ; exige `tensorflow` et `vamp` | Écartée : ancienne, greffon externe |
| `chord-extractor` | **GPLv2** ; Python `<3.12` ; enveloppe le greffon Vamp Chordino compilé | Écartée : licence incompatible avec une distribution permissive |
| `essentia` | **AGPL-3.0** ; bibliothèque lourde | Écartée : licence |
| `madmom` | Dernière release 2018 ; licence « BSD, CC BY-NC-SA » (modèles **non commerciaux**) | Écartée : abandonnée, poids non commerciaux |
| `madmom-infer` | BSD-2, maintenue (2026) ; l'extraction d'accords y est explicitement « hors périmètre pour l'instant » | Écartée : ne fait pas ce qu'on veut |

**Décision :** aucune bibliothèque de modèle n'est ajoutée. Une **base de
référence** est construite avec `librosa` : chroma obtenu par décomposition en
notes (moindres carrés non négatifs, principe du chroma NNLS de Chordino) puis
comparaison à des modèles d'accords. Elle est modeste, documentée comme telle,
et signale ses doutes (ambiguïté, confiance, alternatives) au lieu de les
cacher. La reconnaissance d'accords sur de vrais enregistrements reste le point
le plus faible de l'application ; à revisiter si une option permissive,
maintenue et sans dépendance lourde apparaît.

**Dépendances directes déclarées :** `librosa>=0.10,<1.0`, `numpy>=1.23`,
`scipy>=1.10`. Elles étaient jusqu'ici seulement transitives via `basic-pitch`
alors que le projet les importe directement. La borne `<1.0` n'est pas
cosmétique : `librosa` 1.0 exige Python ≥ 3.12, incompatible avec notre Python
3.11 épinglé (D1).

**Trois défauts de ma première version, trouvés en mesurant** (détails dans
docs/ARCHITECTURE.md § 10) : un simple repliement du spectre lisait les triades
majeures comme des accords de septième majeure (52 accords exacts sur 108) ;
une résolution d'un demi-ton par case faisait déborder chaque note de ~45 % sur
ses voisines ; et la réponse du CQT en f^(-1/2) faisait écraser tout l'accord
par la moindre note de basse.

---

## Questions ouvertes (nécessitent ta décision avant l'implémentation)

### Q1 — Comment récupérer l'audio à partir d'un lien YouTube ? *(résolu le 29/09/2026)*

- `yt-dlp` est l'outil de facto pour cet usage et fonctionnerait techniquement.
- Cet usage touche aux conditions d'utilisation de YouTube (le téléchargement de contenu n'est pas autorisé par les CGU de la plateforme, indépendamment de la faisabilité technique). Je ne tranche pas cette question à ta place — c'est un choix de positionnement du projet (usage strictement personnel/local vs distribution publique de l'outil), pas une question technique.
- Selon ta réponse, l'implémentation change : import de fichier uniquement (le plus simple, retenu par défaut dans le classement MVP), ou ajout de `yt-dlp` derrière une interface remplaçable et clairement documentée comme étant à l'usage de l'utilisateur final sous sa propre responsabilité.

### Q2 — Quel est le matériel cible réel d'exécution ? *(tranché le 29/09/2026 : valeurs par défaut retenues, à revoir si besoin)*

Nécessaire pour trancher la place de Demucs dans le MVP (voir D5) et le nombre de jobs concurrents (D6). Sans cette information, les choix ci-dessus restent des valeurs par défaut prudentes, pas des optimisations.

### Q3 — Portée de la V1 côté instruments *(résolu le 29/09/2026 : guitare/basse uniquement)*

Le prompt initial demande d'évaluer batterie et claviers en plus de guitare/basse. Comme indiqué dans `FEATURE_MATRIX.md`, ces deux instruments sont classés "Expérimental" faute de bibliothèque open source équivalente à `basic-pitch` pour eux. Confirmer si le MVP doit se limiter à guitare/basse (recommandé) ou inclure un prototype batterie/claviers dès la V1.
