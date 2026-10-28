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

17 tâches, budget 30 s / 4 M nœuds, même machine :

| moteur | décidées | temps total sur les décidées |
|---|---:|---:|
| ZDD natif | 15/17 | 6,34 s |
| ZDD + collecte | 13/17 | 5,59 s |
| **SAT** | **16/17** | **0,43 s** |

- **Aucun désaccord** entre moteurs sur les tâches décidées par plusieurs : les trois sont exacts.
- SAT décide `rand14x160_diff`, que les deux moteurs symboliques échouent au budget.
- Ratio médian SAT / ZDD sur les tâches communes : **0,25** (4× plus rapide).
- Le seul échec de SAT (`rand14x160_equiv`, UNSAT) tient au budget de 30 s, pas à l'encodage.

Cas difficiles vérifiés séparément : additionneurs de 24, 28 et 32 bits identiques à eux-mêmes —
équivalents en 0,02-0,04 s ; circuits denses de 16 à 20 fils mutants — différents en moins de
10 ms ; paires équivalentes mais réécrites (UNSAT non trivial) — 0,01 à 0,19 s.

## Ce que SAT ne fait pas

- Il ne produit **pas** d'ANF, donc pas de témoin de degré minimal ni d'inspection polynomiale.
- Il ne donne **pas** de certificat UNSAT vérifiable indépendamment. DRAT/LRAT serait la suite
  naturelle ; ce n'est pas fait, et le rapport ne prétend pas le contraire.
- Il n'est pas installé par défaut : `python-sat` est optionnel, et sans lui `symq.sat.available()`
  vaut `False` et l'appel lève `SatUnavailable`.
