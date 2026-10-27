# Laboratoire ANF / ZDD adaptatif — corpus réels, 27 octobre 2026

**Périmètre :** expériences autonomes et reproductibles pour des circuits
réversibles sur les états de base, avec accumulation exacte de phases de signe
et résultats HMR symboliques selon le sous-modèle qant. **Pas un vérificateur
quantique général**, pas une PR sur le dépôt privé, pas une soumission Kaggle.

## Résultat prioritaire

- **11 circuits publics réels** de tests MQT QCEC (SHA exact enregistré, MIT), dont 5 circuits de développement et 6 réservés ; 44 expériences avec variations contrôlées des entrées libres et 3 expériences synthétiques GF(2¹²).
- **Un cas pathologique `c2_181`** : ANF `set` 226,04 ms → AutoZDD 2,276 ms (≈99×) ; pic Python `tracemalloc` ≈5,04 Mo →0,50 Mo (≈10×). Les mêmes polynômes sont récupérés exactement. La vitesse ne généralise pas aux 10 autres circuits.
- **Sur les 10 autres circuits complets**, l'optimisation `set.symmetric_difference_update` améliore la vitesse en médiane d'environ 1,25× ; elle est le premier levier pratique.
- **Pure-Python ZDD** plus lent d'environ 5× en médiane face au set optimisé sur ces 10 circuits ; la sélection est décisive.
- `packed_only` (combinadic degré 2) refuse correctement les cas exigeant un degré supérieur. `MixedState` fait un repli sparse exact, mais peut être moins rapide à cause des conversions.
- **24 tests pytest passants**, couvrant randomisation déterministe, 11 circuits complets, tables de vérité sur 10 bits, HMR et phases, mutation et limites.

Toutes ces valeurs sont des timings **Python**, hors `mqt.qcec`, hors PolyBoRi/CUDD externes ; aucune preuve de supériorité vis-à-vis de leurs implémentations C++ n'est avancée.

## Démarrage rapide

Python 3.12+ (testé avec 3.13.5), `pytest` pour les tests. Le cœur ne dépend
que de la bibliothèque standard.

```bash
cd anf_corpus_optimization_2026-10-27
PYTHONPATH=. python -m pytest -q tests
PYTHONPATH=. python benchmarks/run_corpus.py \
  --rounds 7 --timeout 5 --memory --out results/my_new_run.json
PYTHONPATH=. python benchmarks/selector_sensitivity.py \
  --rounds 5 --out results/my_new_thresholds.json
```

`--memory` utilise `tracemalloc` **dans un run indépendant** du chronométrage.
Les scripts refusent d'écraser des résultats de mesure existants.

Vérification facultative des sources originales (Internet, à exécuter dans un
contexte autorisé) :

```bash
PYTHONPATH=. python tools/verify_qcec_sources.py
# Ou sans réseau avec un checkout QCEC existant exactement au SHA de provenance :
PYTHONPATH=. python tools/verify_qcec_sources.py --offline-dir /path/to/qcec
```

## Fichiers

- `corpus/qcec_packed.tsv` : 11 séquences publiques normalisées, référence Git par source.
- `corpus/LICENSE_QCEC.txt` : licence MIT, attribution originale.
- `src/optimized.py` : ANF sparse, sparse en place, combinadic + repli exact, tables de vérité.
- `src/zdd.py` : implémentation expérimentale ZDD et sélection avec garde sur les ressources.
- `src/corpus.py` : parseur OpenQASM strict (X/CX/CCX/MCX seulement), lecteur du corpus.
- `src/circuits.py`, `src/field_phase.py`, `src/anf_backends.py` : modèles locaux antérieurs, conservés pour reproduire les expériences sur GF(2¹²).
- `tests/test_symbolic.py` et `tests/test_legacy_anf.py` : 24 tests de propriétés, de compatibilité et de non-régression.
- `benchmarks/run_corpus.py` : 7 backends, corpus public et générateurs synthétiques GF(2¹²).
- `benchmarks/selector_sensitivity.py` : influence du seuil, développement/réserve.
- `results/bench_public_final_v3.json` : résultat de la **dernière version testée** ; `results/selector_sensitivity.json` : seuils.
- `docs/CORPORA_RECENTS.md` : inventaire 2026, couverture, licences, sources réelles immédiatement utilisables.
- `docs/COMPARAISON_EXISTANT.md` : protocole, tableau de résultats, limites.
- `docs/AGENT_QANT.md` : handoff intégré aux règles multi-agents du dépôt.
- `tools/replay_qant_fixture.py` : test offline optionnel du fragment privé sur un checkout autorisé et SHA vérifié, **non exécuté ici**.
- `tools/verify_qcec_sources.py` : comparaison du corpus à l'OpenQASM original et à son Git blob SHA ; **non exécuté ici** faute de réseau disponible.
- `MANIFEST.sha256` : intégrité de l'archive créée.

## Mesure de succès et recommandations

**Intégration court terme** : préférer le XOR en place dans le vérificateur qant,
si et seulement si les tests et le profil réel confirment le gain. **Moyen terme** :
backend ZDD à activation conditionnelle là où la densité ANF explose ; garder
les ancillas, corrections HMR et phases exactes. **Recherche/publication** :
étendre le corpus à `andigu/uncompute` (circuits 2026 avec mesures et phases),
appairer les comparaisons aux vraies bibliothèques PolyBoRi/CUDD et MQT QCEC,
et définir une politique de sélection validée sur un corpus tenu à l'écart.

Les fichiers sous `/mnt/data` sont des résultats de travail ; **aucune
modification du dépôt `yoch/qant` n'a été demandée ou effectuée.**
