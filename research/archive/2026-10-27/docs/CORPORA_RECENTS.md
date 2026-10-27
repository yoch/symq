# Corpus candidats identifiés au 27 octobre 2026

## Corpus effectivement exécuté dans ce laboratoire

**MQT QCEC, commit `98d6784176bfeb6ef923d4d0220e8d486dc1982f`**
- Source : https://github.com/munich-quantum-toolkit/qcec/tree/main/test/circuits/original
- 11 circuits réversibles : 5 utilisés pour orienter le seuil, 6 réservés.
- 11 circuits acceptés dans leur intégralité après normalisation stricte des portes `X/CX/CCX/MCX` ; **toutes les variables de chaque circuit sont symboliques** sur la variante `full_*`.
- 44 expériences couvrant ces 11 circuits (domaines complets ou partiellement fixés) et 3 synthétiques GF(2¹²) ; voir `results/bench_public_final_v3.json`.
- Attribution et MIT dans `corpus/LICENSE_QCEC.txt`.
- Attention à l'âge des exemples originaux : le référentiel est actuel, les algorithmes ne sont pas tous nouveaux.

## Sources 2026 vérifiées, mais NON chronométrées par notre moteur

**Gu et al., `andigu/uncompute` (arXiv:2610.22367, octobre 2026)**
- https://github.com/andigu/uncompute
- Épinglage : `64b5a13aa249f1360846657392e6c66817b26d0f`.
- Sources et flux `*.ops.xz` présents dans les dossiers de tâches. Exemples vérifiés dans l'arbre distant :
  - `tasks/coulomb-potential/circuits/discovered/circuit.ops.xz` — blob Git `3f0a737688f68da2a5b40fc699623891e8518196` (12 452 octets compressés).
  - `tasks/hhl-angle/circuits/discovered/circuit.ops.xz` — `ac748992ac57d1820df168040a5000c62c6297fd` (38 344 octets).
  - `tasks/gaussian/circuits/discovered/circuit.ops.xz` — `f8bf39b23ce1e65400b105e1e13c34e387fa720c` (23 764 octets).
  - `tasks/dqi-reed-solomon/circuits/discovered/circuit.ops.xz` — `51350f16ed25e8259ebce462568554611e126bdc` (15 644 068 octets).
- **Priorité maximale pour la pertinence qant**, parce que ces circuits emploient l'effacement en base X et les corrections de phase.
- Reste à importer le format d'opérations original à l'aide du toolchain `uncompute`/Kickmix épinglé, définir les entrées libres et sélectionner des fenêtres de mesure compatibles. **Aucun test de ces flux n'a été exécuté ici**, ni aucune vitesse revendiquée.
- Outils et sources Apache-2.0 ; conserver attribution et lire les conditions du dataset avant redistribution.

**QuantumSemEval2026**, 260 paires d'équivalence étiquetées
- Site : https://quitttcat.github.io/QuantumSemEval2026/
- Git : https://github.com/QuitttCat/QuantumSemEval2026 — commit `bc9006a77255e1e19694fb3d4dfe38547c458575`.
- Audit de compatibilité **sur huit paires sélectionnées seulement** (6 équivalentes, 2 non équivalentes) : **0/8 intégralement couvertes**. Les portes bloquantes comprennent `h`, `rz`, `rccx`, `cswap`, `ry`, des contrôles de portes non classiques et des paramètres arbitraires.
- Notre ANF suit une base booléenne avec phase de signe ; ne jamais réinterpréter les portes quantiques générales comme des opérations booléennes. Les huit refus sont corrects ; **ne pas extrapoler 0/8 à l'ensemble des 260 paires**.
- Une étude d'extension HPS/path-sum serait une autre recherche, et non une optimisation locale du backend ANF.

**MQT Bench / MQT QCEC (`mqt.bench`, `mqt.qcec`)**
- https://mqt-bench.app/ et https://github.com/munich-quantum-toolkit/qcec
- Source de véritables générateurs de circuits arithmétiques, de QFT et de circuits dynamiques. Une minorité est directement réversible `X/CX/CCX`, le reste comprend Hadamard/rotations et est hors modèle.
- Pour un protocole tiers, installer `mqt.qcec` sur un environnement compatible et vérifier des paires de circuits ; **ce laboratoire n'a pas chronométré sa bibliothèque C++**.

**RevLib / RevKit**
- https://www.revlib.org/realizations.php
- Plusieurs centaines de réalisations réversibles classiques (format REAL ; sous-bibliothèques NCT/MCT). Excellent corpus complémentaire *historique*, pas une nouveauté 2026. À importer strictement en contrôlant constantes, fils négatifs et sous-circuits avant benchmark.

## Critères d'inclusion pour une publication

1. Source et licence publics ; SHA immuable, provenance du générateur enregistrée.
2. Toutes les portes et dépendances classiques d'une instance doivent appartenir au **modèle explicitement pris en charge**, sinon `UNSUPPORTED` (pas d'écrasement de portes).
3. Indiquer `full_input`, `restricted_input` ou `toy_synthetic` ; ne pas les agréger sans stratification.
4. Séparer temps du calcul symbolique, génération, vérification et mémoire. Signaler les cas où le backend n'est pas applicable.
5. Comparer à un ZDD industriel réel (PolyBoRi/CUDD ou équivalent), au vérificateur natif qant et au backend DD de MQT QCEC lorsqu'il prend en charge le même contrat.
