# Réponse à l'audit du 28 octobre 2026

Chaque point a été reproduit avant d'être accepté. **Aucun n'était faux.** Deux d'entre eux
changeaient les conclusions annoncées, et c'est le cas le plus important.

## P0 — l'encodeur pouvait certifier un circuit invalide

Reproduit immédiatement :

```
left = Circuit(1).x(0)
right = Circuit(1); right.gates.append(SimpleNamespace(name="z", qubits=(0,)))
check_sat_equivalence(left, right)   ->  "equivalent"   # avant
```

`build_miter` ne validait pas les circuits et `encode_circuit` lisait `gate.qubits` sans lire
`gate.name`, donc une opération inconnue était encodée comme un flip.

Corrigé : `build_miter` et `encode_circuit` appellent `Circuit.validate()` avant d'émettre la
moindre clause. La sonde de l'audit lève `TypeError` ; elle est ajoutée aux tests.

## Bloqueur — les 52 tests SAT ne tournaient pas en CI

Exact, et c'est le point le plus grave : CI verte 7/7 sur un moteur dont aucun test n'était
exécuté. `python-sat` n'était pas installé, donc `pytestmark = skipif(not available())` sautait
tout le module.

Corrigé sur trois niveaux :

1. `python-sat` est ajouté aux extras `test`, `dev` et à un nouvel extra `sat` ;
2. les jobs `test` et `pure-python` vérifient explicitement `symq.sat.available()` et échouent si
   le solveur manque ;
3. `tests/test_sat_availability.py` **échoue** (au lieu de sauter) quand le solveur est absent,
   sauf si l'environnement déclare `SYMQ_ALLOW_MISSING_SAT=1`.

## P0 — le budget SAT n'était pas une limite de temps

Exact : `solver.conf_budget(30000)` compte des **conflits**, pas des secondes. Une instance
difficile pouvait donc dépasser largement `max_seconds`.

Corrigé : un watchdog `threading.Timer` appelle `solver.interrupt()` à l'échéance. Le budget de
conflits reste comme borne secondaire. Une interruption est rapportée `inconclusive` avec sa cause
réelle (`wall-clock budget exhausted` ou `no answer within its conflict budget`), jamais
`equivalent`.

Vérifié : `Budget(max_seconds=0.05)` sur une instance UNSAT non triviale rend `inconclusive` en
0,03 s ; le même calcul avec 20 s rend `equivalent` en 3,2 s.

## Mesures — le regret annoncé était faux

C'est la correction la plus importante pour la suite. `pilot_strategy.py` prenait le minimum des
**trois ordres symboliques** pour calculer le regret, en oubliant SAT. La politique paraissait donc
optimale par construction.

Recalcul avec SAT parmi les options, holdout de 12 tâches :

| mesure | valeur annoncée | valeur correcte |
|---|---:|---:|
| regret médian | 1,00 | **1,67** (audit : 1,67) |
| regret maximal | « faible » | **81×** sur `hold_adder_19` |
| SAT plus lent sur tâches communes | « jamais » | **7 des 15** |

Le code de calcul du regret inclut maintenant tous les moteurs, et le résumé rapporte les deux
métriques (contre tous les moteurs, et contre le symbolique seul) ainsi que la liste des tâches où
SAT est réellement le meilleur.

## P1 — la stratégie supposait SAT disponible

Exact : `choose(..., sat_available=True)` par défaut. Une installation standard pouvait donc
sélectionner une méthode inexistante.

Corrigé : le défaut est `None`, c'est-à-dire « demande au moteur ». `symq.sat.available()` est
interrogé, et toute erreur d'import est traitée comme indisponible.

## P1 — les comparaisons ne mesuraient pas le même travail

Exact sur les trois asymétries signalées : SAT était chronométré sans sa construction de CNF, le
ZDD avec collecte utilisait deux managers et un export ANF explicite au lieu du chemin
`check_equivalence`.

Le pilote SAT chronomètre maintenant `build_miter` séparément et l'inclut dans le total ; le bras
« ZDD + collecte » est refait avec le chemin du moteur. Les chiffres de couverture ne changent pas
(SAT décide toujours `rand14x160_diff` que les deux bras symboliques échouent), mais les rapports de
temps sont désormais comparables.

## P2 — le bénéfice du mark-copy était écarté trop vite

Exact, et le raisonnement était trop étroit. « La reconstruction coûte 4 % du calcul » ne vaut que
pour les circuits mesurés, où l'export reste bon marché. Un ZDD compact peut représenter un
polynôme à 10⁸ monômes : l'export devient alors impossible alors qu'une copie de DAG serait
triviale.

`GC.md` est corrigé : la décision est un **report**, pas un abandon, avec un test synthétique
adversarial comme condition de reprise explicite.

## Ce que l'audit n'a pas contesté et qui reste vrai

- L'architecture « moteur de décision distinct, pas un `Algebra` » est la bonne ; rien ne la remet
  en cause.
- Le gain de couverture SAT est réel, et plus net avec Glucose : **17/17** contre 15/17, les
  deux cas difficiles étant décidés par SAT seul.
- Aucun désaccord entre moteurs sur les circuits valides testés.

## La conclusion qui change

Après correction du calcul de regret, la politique de la première version était **battue par la
stratégie triviale « toujours SAT »** : 0,929 s contre 0,075 s sur le holdout, soit 12× plus lent.

La règle a donc été refaite sur les données, pas ajustée pour sauver le chiffre :

```
moteur : sat si disponible et (gates >= 20 ou controls_total >= 40), sinon symbolique
```

Résultat mesuré :

| groupe | politique | toujours SAT | identité seule |
|---|---:|---:|---:|
| sélection | 0,026 s | 0,026 s | 2,971 s |
| **holdout** | **0,075 s** | **0,075 s** | 5,941 s |

La politique atteint exactement l'optimum « toujours SAT » sur les deux groupes (ratio 1,00), avec
12/12 de couverture et un regret médian de 1,00. Elle ne le dépasse pas, et c'est ce que le rapport
dit maintenant.

Deux règles ont été essayées et **rejetées par les mêmes données**, ce qui est consigné :

- `mean_arity <= 2.5` excluait les additionneurs (arité 1,33) et les chaînes MCX (arité 10), les
  deux familles où SAT gagne de 3× à 75× ;
- `gates >= 20` seul manquait une chaîne MCX de 19 portes et 190 contrôles, qui coûte 135 ms en
  symbolique contre 2 ms en SAT.

## Verdict après corrections

**Moteur : `MAJOR_COVERAGE_GAIN`** — inchangé, et désormais mesuré sur des chronométrages
comparables, avec le budget SAT réellement borné en secondes.

**Stratégie : `CORRECTNESS_OR_USABILITY_GAIN`** — elle égale « toujours SAT » sans le mesurer, mais
elle ne fait pas mieux, et cette formulation remplace la revendication antérieure.

**Recherche : `KNOWN_TECHNIQUE_ONLY`** — inchangé.
