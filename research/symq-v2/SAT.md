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
| `inconclusive` | budget épuisé ou solveur sans réponse décisive | **jamais** une preuve d'équivalence |

Un modèle qui ne produit pas de différence réelle lève `InternalInconsistency` : c'est un bug de
l'encodage, pas un verdict.

## Résultats (`RESULTS/sat_pilot.json`, moteur actuel : Glucose 4.2, python-sat 1.9.dev17)

17 tâches, budget temporel **coopératif** de 30 s ; construction du CNF incluse dans la colonne SAT. Il s'agit d'un pilote ancien, pas d'une mesure du HEAD final.

| moteur | décidées | temps total sur les décidées |
|---|---:|---:|
| ZDD natif | 15/17 | 6,34 s |
| ZDD + collecte | 13/17 | 5,55 s |
| **SAT (Glucose 4.2)** | **17/17** | **2,77 s** |

Ce qui est établi :

- **Couverture** : SAT décide **les deux** cas que les deux moteurs symboliques échouent au
  budget — `rand14x160_diff` en 0,14 s et `rand14x160_equiv` (UNSAT) en **1,98 s**. CaDiCaL
  échouait sur ce dernier ; Glucose le termine. C'est le gain de la mission, et il est plus net
  qu'annoncé avec l'ancien solveur.
- **Aucun désaccord** entre moteurs sur les tâches décidées par plusieurs.
- **Vitesse** : médiane du ratio SAT/ZDD de **1,39** sur les 15 tâches communes, et SAT est plus
  lent sur **8 des 15**. Le chiffre antérieur de 0,69 correspondait à CaDiCaL et n'est plus
  valable : Glucose est plus robuste sur les instances difficiles, plus lent sur les petites.

Une campagne antérieure, mesurée avec CaDiCaL, donnait 16/17 et un ratio de 0,69.
**Ces chiffres historiques sont accessibles dans l'historique Git** ; le fichier actuel
`RESULTS/sat_pilot.json` contient le pilote Glucose 4.2 et ne représente pas
le code exact des derniers commits intégrés. L'absence de solveur lève
`SatUnavailable` ; les erreurs de cohérence internes lèvent une exception.

## Ce que SAT ne fait pas

- Il ne produit **pas** d'ANF, donc pas de témoin de degré minimal ni d'inspection polynomiale.
- Il ne donne **pas** de certificat UNSAT vérifiable indépendamment. DRAT/LRAT serait la suite
  naturelle ; ce n'est pas fait, et le rapport ne prétend pas le contraire.
- Il n'est pas installé par défaut : `python-sat` est optionnel, et sans lui `symq.sat.available()`
  vaut `False` et l'appel lève `SatUnavailable`.

## Limite temporelle et statut expérimental

Le délai de `Budget.max_seconds` est **coopératif** pour l'appel complet :
construction CNF/solveur, résolution, modèle, vérification du témoin et nettoyage.
Il n'interrompt pas de force un appel Python ou C déjà engagé et ne constitue
pas un plafond strict garanti ; une vérification terminée hors délai devient
`inconclusive`. Les limites symboliques `max_nodes` et `max_terms` ne sont
pas des limites CNF et ne sont pas appliquées au moteur SAT.

La campagne de 17 tâches reste un **pilote exploratoire** : le script construit le miter
deux fois dans le bras SAT, tandis que le bras ZDD avec collecte exporte les ANF
au lieu d'employer la voie de production par paires. Il faut une nouvelle
comparaison appariée et identifiée par les SHA exacts avant toute revendication
comparative définitive.
