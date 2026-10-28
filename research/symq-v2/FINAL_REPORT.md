# Rapport final — SymQ V2, 28 octobre 2026

## 1. HEAD de référence

`main` = **`ddfe7aa`** (« Merge #63: safe native collection, cache and ordering integration »).
Branche de travail `cursor/auto-strategy-f132`, construite sur `main` avec la branche SAT fusionnée.
ABI natif 4, extension GCC 13.3.0 `-O3`. Suite sur `main` : **2 935 passés, 2 ignorés**. Suite avec
ce travail : **3 005 passés, 2 ignorés**.

## 2. PR ouvertes

| PR | contenu | état |
|---|---|---|
| SAT | `src/symq/sat/`, 52 tests, pilote | prête, CI à vérifier |
| Stratégie + documentation | `src/symq/strategy.py`, 18 tests, `research/symq-v2/` | dépend de SAT |

Aucune fusion effectuée. #26 et #27 ne sont pas touchées.

## 3. Améliorations effectivement implémentées

**SAT comme moteur de décision** (`src/symq/sat/`). Encodage Tseitin total, miter, trois issues
distinctes, témoin rejoué par `Circuit.run`, `InternalInconsistency` si un modèle n'est pas un
contre-exemple. Optionnel : sans `python-sat`, `available()` vaut `False` et l'appel lève.

**Contrats de vérification** (`Contract`) : entrées constantes, sorties observées, fils restaurés,
permutation de fils, validation stricte. Testés sur le vrai additionneur Cuccaro.

**Stratégie automatique** (`symq.strategy.choose`) : features en une passe, deux règles énoncées,
déterministes, aucune sémantique devinée depuis un nom.

**Collecte intégrée au moteur** (déjà dans `main`, mesurée ici) : `collect_every` fonctionne depuis
`check_equivalence`, avec un découpage adaptatif.

## 4. Ce qui reste expérimental

- La stratégie : elle est validée sur un holdout de tailles inédites, pas sur des architectures
  indépendantes. Elle n'est pas le défaut.
- La collecte : opt-in, avec une régression de temps de 1,44× sur un circuit sur quatre.
- Les contrats : implémentés et testés, mais aucun corpus de composants réels ne les utilise encore.

## 5. Quels nouveaux circuits SymQ peut vérifier

| circuit | avant | après |
|---|---|---|
| `rand14x160_diff` (14 fils, 160 portes) | budget dépassé sur les deux moteurs symboliques | **décidé par SAT** |
| `hold_rand15x180_diff`, `hold_rand17x220_diff` | hors de portée du symbolique au budget | **décidés par SAT** |
| additionneurs 24 / 28 / 32 bits | ZDD : coûteux ou hors budget selon l'ordre | **0,02-0,04 s par SAT** |
| 14×200 avec collecte | budget dépassé, 6 920 Mio | **termine, 931 Mio** |

## 6. Temps et mémoire réellement économisés

| mesure | avant | après | gain |
|---|---:|---:|---|
| tâches d'équivalence décidées (17, budget 30 s) | 15 | **16** | +1 tâche |
| temps SAT / ZDD sur tâches communes | — | — | **0,25 (4×)** |
| politique contre défaut (`identity`+symbolique) | 1,933 s | 1,068 s | **1,81×** |
| pic RSS, 14×200 avec collecte | 6 920 Mio | 931 Mio | **7,4×** |
| regrets de la politique, holdout | — | médian 1,00 | atteint toujours l'optimum |

## 7. Familles où l'on régresse

- **SAT** : aucun cas mesuré où SAT est plus lent que le symbolique sur une tâche décidée par les
  deux, mais `rand14x160_equiv` (UNSAT) échoue au budget de 30 s là où un ZDD aurait pu, en
  principe, terminer avec plus de mémoire.
- **Collecte** : 1,44× plus lente sur `14x200 seed 21`.
- **`last_use`** : 1,58× plus lent sur les chaînes MCX et 1,105× sur les incrémenteurs — d'où la
  règle qui l'exclut de ces formes.

## 8. SAT apporte-t-il une couverture complémentaire ?

**Oui, et c'est le résultat le plus net de la mission.** 16/17 contre 15/17, un circuit que les deux
moteurs symboliques échouent, 4× plus rapide sur les tâches communes, aucun désaccord. Le
mécanisme est clair : l'encodage est linéaire en portes, alors que le coût symbolique est piloté par
la taille des familles de monômes.

Ce que SAT n'apporte pas : pas d'ANF, pas de témoin de degré minimal, pas de certificat UNSAT
indépendant. Les deux moteurs sont complémentaires, pas substituables.

## 9. Les contrats permettent-ils de traiter des problèmes auparavant inexpressibles ?

**Oui, au sens de l'exprimabilité.** Avant, vérifier un gadget sous précondition obligeait à
construire un circuit englobant qui force l'entrée, ou à accepter un verdict sur un domaine plus
large que le domaine réel. Maintenant le domaine, les sorties observées et l'obligation de nettoyage
s'écrivent dans le contrat, et sont validés strictement.

Le gain n'est pas en vitesse : c'est qu'un problème mal posé devient bien posé.

## 10. La politique automatique fonctionne-t-elle sur des architectures indépendantes ?

**Non, et le rapport ne le prétend pas.** Elle fonctionne sur un holdout de **tailles inédites de
générateurs connus** (12/12, regret 1,00). C'est une extrapolation, pas une généralisation. Aucun
circuit issu d'un compilateur réel n'a été utilisé.

## 11. Le collecteur natif est-il plus utile que le rebuild ?

**La question est mal posée, et la mesure le montre.** Le transfert par monômes coûte **4 % du temps
d'un run** (13 ms par collecte, 25 collectes sur 7,85 s). Un mark-copy parfait ne peut donc gagner
que 4 %, alors qu'il faut payer son écriture, ses tests et son risque d'invalidation d'identifiants.

Ce qui change la couverture, ce n'est pas *quel* collecteur, c'est *collecter* : c'est fait, en
option, avec 7,4× de mémoire en moins et un circuit qui termine là où il échouait.

## 12. Une primitive scientifique nouvelle a-t-elle été découverte ?

**Non.** Le critère de canal HMR reste le seul résultat non trivial des missions précédentes, et il
n'a toujours pas de programme réel qui l'exige. La décomposition avec certificats n'a produit aucune
primitive : les interfaces compactes ne se présentent pas là où l'expansion échoue
(`INTERFACE_PROOFS.md`).

## 13. Intégrer, reporter, abandonner

**Intégrer** : SAT, contrats, stratégie, documentation.
**Reporter** : mark-copy (condition : collecte > 20 % d'un run), certificat UNSAT, largeur > 64,
HMR sur corpus réel.
**Abandonner** : décomposition avec certificats, en l'état.

## Table comparative

| Cas | Backend historique | Nouvelle stratégie | Statut avant → après | Temps | Pic RSS | Correction |
|---|---|---|---|---|---|---|
| `rand14x160_diff` | ZDD natif | SAT | budget → **décidé** | — → 0,02 s | non mesuré par moteur | témoin rejoué |
| `hold_rand17x220_diff` | ZDD natif | SAT | budget → **décidé** | — → 0,04 s | — | témoin rejoué |
| `hold_adder_19` | `identity` | `last_use` | décidé → décidé | 1,358 → 0,665 s | — | ANF identique |
| `hold_mcxchain_20` | `identity` | `identity` (règle) | décidé → décidé | 0,140 → 0,140 s | — | ANF identique |
| 14×200 g7 | sans collecte | `collect_every=400k` | budget → **termine** | 65 → 44 s | 6 920 → **931 Mio** | table de vérité, 16 384 entrées |
| 14×200 g21 | sans collecte | `collect_every=400k` | budget → **termine** | — → 107 s | 3 448 → 254 Mio | table de vérité |

Toutes les lignes sont dans `RESULTS/sat_pilot.json`, `RESULTS/strategy_pilot.json`, et
`research/innovation/2026-10-28/RESULTS_C7.json` avec le SHA de la campagne.

## Verdicts

**Moteur : `MAJOR_COVERAGE_GAIN`.** Des circuits que le moteur historique ne décidait pas au budget
sont maintenant décidés, par deux mécanismes distincts (SAT pour la décision, collecte pour la
mémoire), et vérifiés par oracles indépendants.

**Recherche : `KNOWN_TECHNIQUE_ONLY`.** Aucune primitive nouvelle ; le critère HMR reste un
candidat sans utilisateur démontré, et la décomposition est un résultat négatif argumenté.
