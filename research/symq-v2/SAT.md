# SAT — moteur de décision exact, et ce qu'il apporte réellement

## Pourquoi un moteur de décision et pas un backend

Un `Algebra` promet `to_anf`. Un solveur SAT ne peut pas tenir cette promesse sans énumérer ses
modèles, ce qui est exactement ce qu'on veut éviter. Le paquet `symq.sat` expose donc une fonction
de décision, `check_sat_equivalence`, et non une représentation interchangeable.

## L'encodage

Une variable par (fil, étape). Une porte `(C, t)` avec `q = AND(C)` définit **complètement** la
couche suivante :

```
q      <-> AND des contrôles          (trois clauses standard, ou une variable forcée à vrai)
next_t <-> t XOR q                    (quatre clauses)
next_w <-> w        pour w != t       (aucune clause : la même variable est réutilisée)
```

La réutilisation de la variable pour les fils non touchés est ce qui rend l'encodage linéaire en
portes ; la définition complète de `next_t` est ce qui garantit que **tout modèle est une
exécution**.

**Une version précédente était fausse** et les tests exhaustifs l'ont attrapée : elle n'écrivait
que l'implication `q -> (next_t = t XOR 1)`, ce qui laissait le solveur choisir `next_t` librement
quand `q` était faux. Sur un circuit de trois portes, SAT déclarait équivalents deux circuits qui
diffèrent sur toutes les entrées. La correction est la biconditionnelle ci-dessus ; le cas est
gardé comme test de régression.

## Le miter et ses trois issues

Pour `L` et `R` de même largeur, on identifie les variables d'entrée des deux circuits, puis on
ajoute la clause « au moins une sortie observée diffère ». Trois issues, jamais confondues :

| issue | ce qu'elle vaut | ce qu'elle n'est pas |
|---|---|---|
| `different` | un modèle a été **rejoué par `Circuit.run`** et diffère vraiment | — |
| `equivalent` | le miter est UNSAT pour l'encodage et le contrat déclarés | pas un certificat UNSAT indépendant |
| `inconclusive` | pas de solveur, budget épuisé, erreur du solveur | **jamais** une preuve d'équivalence |

Un modèle qui ne produit pas de différence réelle lève `InternalInconsistency` : c'est un bug de
l'encodage, pas un verdict.

## Résultats (`RESULTS/sat_pilot.json`)

17 tâches, budget 30 s **réel** / 4 M nœuds, même machine. La construction du CNF est chronométrée
séparément et **incluse** dans la colonne SAT, comme dans les colonnes symboliques ; la première
version ne comptait que le temps du solveur, ce qui rendait les colonnes incomparables.

| moteur | décidées | temps total sur les décidées |
|---|---:|---:|
| ZDD natif | 15/17 | 6,34 s |
| ZDD + collecte | 13/17 | 5,59 s |
| **SAT** | **16/17** | **0,45 s** |

Ce qui est établi :

- **Couverture** : SAT décide `rand14x160_diff`, que les deux moteurs symboliques échouent au
  budget. C'est le gain réel de la mission.
- **Aucun désaccord** entre moteurs sur les tâches décidées par plusieurs : les trois sont exacts.
- **Médiane SAT / ZDD sur les tâches communes : 0,69**, soit 1,44× plus rapide — et non 4× comme
  annoncé avant que la construction du CNF soit comptée.

Ce qui n'est **pas** établi, et que l'audit a correctement relevé :

- **SAT est plus lent sur 7 des 15 tâches communes**, parfois de plus de 20×. Sur les petits
  circuits, le coût fixe de l'encodage domine : `adder_8_same` coûte 0,2 ms d'encodage pour 3,4 ms
  de solveur, là où le symbolique prend 0,5 ms. La phrase « SAT n'est jamais plus lent » était
  fausse et a été retirée.
- Le seul échec de SAT (`rand14x160_equiv`, UNSAT) tient au budget de 30 s, pas à l'encodage.

Cas difficiles vérifiés séparément : additionneurs de 24, 28 et 32 bits identiques à eux-mêmes —
équivalents en 0,02-0,04 s ; circuits denses de 16 à 20 fils mutants — différents en moins de
10 ms ; paires équivalentes mais réécrites (UNSAT non trivial) — 0,01 à 0,19 s.

## Budget

`max_seconds` est une **vraie** limite de temps : un watchdog appelle `solver.interrupt()` à
l'échéance. La version précédente passait `conf_budget(max_seconds * 1000)`, qui compte des
**conflits** et non des secondes — une instance difficile pouvait donc dépasser largement le
budget annoncé. Le budget de conflits subsiste comme borne secondaire. Une interruption rend
`inconclusive` avec sa cause réelle, jamais `equivalent`.

## Ce que SAT ne fait pas

- Il ne produit **pas** d'ANF, donc pas de témoin de degré minimal ni d'inspection polynomiale.
- Il ne donne **pas** de certificat UNSAT vérifiable indépendamment. DRAT/LRAT serait la suite
  naturelle ; ce n'est pas fait, et le rapport ne prétend pas le contraire.
- Il n'est pas installé par défaut : `python-sat` est optionnel, et sans lui `symq.sat.available()`
  vaut `False` et l'appel lève `SatUnavailable`.
