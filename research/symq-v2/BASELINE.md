# Baseline — état vérifié avant cette mission

## Dépôt

| item | valeur |
|---|---|
| `main` au moment du cadrage | `ddfe7aa` — « Merge #63: safe native collection, cache and ordering integration » |
| ABI natif | 4 (`_zdd.ABI_VERSION`) |
| extension | GCC 13.3.0, `-O3`, SHA-256 du `.so` enregistrée dans chaque `environment.json` |
| tests sur `main`, arbre propre | **2 935 passés, 2 ignorés** (`pytest tests/ --ignore=tests/test_corpus.py`) |
| CI de #63 | 7/7 verte |
| PR ouvertes | #26 (benchmarks), #27 (manuscrit) — non touchées |

## Ce que le moteur sait faire avant cette mission

- simulation symbolique exacte du fragment X/CX/CCX/MCX, backend natif ou Python ;
- comparaison de deux circuits et témoin de degré minimal, revérifié concrètement ;
- cache d'opérations lossless par défaut, borné en option (`cache_limit`) ;
- collecte optionnelle par reconstruction (`collect_every`), contrat « un manager, un run » ;
- ordres `identity`, `reversed`, `last_use` ;
- budgets temps / nœuds / monômes, refus explicite plutôt qu'approximation ;
- moteur de phase HMR de référence, avec oracle de densité indépendant.

## Ce qu'il ne sait pas faire, et que cette mission vise

1. **Décider une équivalence sans construire les ANF.** Chaque verdict passe aujourd'hui par deux
   simulations complètes ; une paire dont les fonctions intermédiaires explosent est hors de portée
   même si les circuits sont triviaux.
2. **Restreindre le problème.** Aucun moyen de dire « je ne vérifie que ces sorties, sous cette
   précondition, et j'exige que cette ancilla redevienne propre ».
3. **Choisir une méthode.** Les trois ordres et l'activation de la collecte sont des réglages
   laissés à l'utilisateur, sans règle.

## Mesures de départ, reprises des campagnes précédentes

Elles ne sont pas refaites ici et ne servent que de contexte ; les chiffres de cette mission sont
dans `RESULTS/` avec leur propre SHA.

| mesure | valeur | provenance |
|---|---|---|
| `last_use` contre `identity`, additionneurs | 0,017 (58×) | `research/engineering/2026-10-28/RESULTS_ORDER_CORRECTED.json` |
| `last_use` contre `identity`, chaînes MCX | 1,577 (58 % plus lent) | idem |
| cache borné contre lossless, petits circuits | 0,93 | `RESULTS_CACHE_SEPARATED.json` |
| collecte par porte, 14×200 | 931 Mio contre 6 920 Mio | `research/innovation/2026-10-28/RESULTS_C6.json` |

Le domaine exact de ces chiffres est celui de leur campagne : 4-vCPU Intel Xeon, Linux 6.12,
CPython 3.12.3. Aucun n'est transposé à une autre machine.
