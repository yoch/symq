# SymQ V2 — état, périmètre et résultats

Branche de travail : `cursor/sat-verification-f132`, construite sur `main` à `ddfe7aa` (PR #63).

## Ce qui a été fait, en une page

| axe | état | preuve |
|---|---|---|
| **SAT** — moteur de décision exact | **implémenté** | `src/symq/sat/`, 52 tests, `RESULTS/sat_pilot.json` |
| **Contrats** — domaine, sorties, ancillas | **implémenté** | `Contract` dans `sat/encoding.py`, testé sur le vrai additionneur Cuccaro |
| **Mark-copy natif** — collecteur sans export | **non commencé** | reporté, voir `GC.md` |
| **Décomposition avec certificats** | **non commencé** | reporté, voir `INTERFACE_PROOFS.md` |
| **HMR étendu** | **non commencé** | arrêt documenté, voir `DECISIONS.md` |

## Résultats principaux, chiffrés

**SAT augmente la couverture.** Sur 17 tâches d'équivalence à 30 s / 4 M nœuds :

| moteur | tâches décidées | temps total |
|---|---:|---:|
| ZDD natif | 15/17 | 6,34 s |
| ZDD + collecte | 13/17 | 5,59 s |
| **SAT** | **16/17** | **0,43 s** |

Aucun désaccord entre les trois moteurs sur les tâches décidées par plusieurs. SAT décide
`rand14x160_diff`, que les deux moteurs symboliques échouent. En temps, CNF inclus, il est
**1,44× plus rapide** en médiane sur les tâches communes (ratio 0,69) — et **plus lent sur 7 des
15**, car son coût fixe d'encodage domine sous la milliseconde.

## Ce qui n'est pas fait, et pourquoi

Le collecteur *mark-copy* natif et la décomposition avec certificats sont les deux axes qui
restent. `DECISIONS.md` explique l'arbitrage : le collecteur actuel par reconstruction est déjà
dans le moteur et fonctionne ; le mark-copy est une optimisation de son coût de transfert
(0,3 % d'un run mesuré), pas un changement de couverture. L'axe scientifique D n'a pas de
primitive identifiée, et la mission demande explicitement de ne pas construire de framework sans
preuve d'intérêt.

## Fichiers

`README.md` (ce fichier), `BASELINE.md`, `SAT.md`, `CONTRACTS.md`, `STRATEGY.md`, `GC.md`,
`INTERFACE_PROOFS.md`, `DECISIONS.md`, `INTEGRATION.md`, `FINAL_REPORT.md`, `RESULTS/`.
