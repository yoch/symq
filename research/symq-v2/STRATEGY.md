# Stratégie automatique — état expérimental

**Décision : `EXPERIMENTAL — NO DEMONSTRATED SELECTOR GAIN`.**

Les caractéristiques structurelles et les heuristiques d'ordre sont correctes et utiles. La
sélection automatique entre moteurs, en revanche, **ne démontre aucun avantage** : sur tous les
corpus mesurés, la règle finit par choisir SAT, ce qui reproduit « toujours SAT » au lieu de le
battre. L'API reste une recommandation, sans dispatch automatique et sans changement de
comportement par défaut.

## Les deux décisions sont séparées

Choisir un ordre pour un backend déjà choisi et choisir un moteur pour une tâche ne demandent pas
les mêmes indices. Les deux sont dans `src/symq/strategy.py`, chacun avec sa règle énoncée.

## Les caractéristiques, en une passe

| feature | ce qu'elle capte |
|---|---|
| `last_use_spread` | écart-type des positions de dernier usage, normalisé. Proche de 0 : tous les fils finissent ensemble (cascade). Grand : structure étagée. |
| `distinct_controls` | nombre de fils utilisés comme contrôle |
| `mean_arity` | contrôles par porte |
| `depth_estimate` | **profondeur réelle** : longueur du plus long chemin de dépendances, par fil et en une passe |
| `width`, `gates`, `used_wires`, `max_arity`, `first_use_spread` | taille et forme |

`depth_estimate` a été corrigé après audit : l'implémentation précédente ne comparait que des
portes **consécutives**, ce qui n'est pas la profondeur. Sur `X(0), X(1), X(0)`, l'ancienne donnait
1, la définition par fil donne 2 — et c'est ce cas qui sert de test.

## Les règles

```
ordre   : last_use  si spread >= 0.12 et distinct_controls >= 3 et gates >= 24
          reversed  si spread >= 0.12 et gates >= 24
          identity  sinon
moteur  : sat       si le solveur est disponible et (gates >= 20 ou controls_total >= 40)
          symbolic  sinon
```

Aucune règle ne lit le nom du circuit ni la position d'un fil pour deviner une sémantique
arithmétique : tout vient de la forme de la liste de portes. `choose()` interroge
`symq.sat.available()` au lieu de supposer SAT installé.

## Résultats mesurés (`RESULTS/strategy_pilot.json`, Glucose 4.2)

| mesure | sélection (6) | holdout (12) |
|---|---:|---:|
| tâches décidées par la politique | 6/6 | **12/12** |
| décidées par `identity` seul | 5/6 | 10/12 |
| décidées par SAT seul | 6/6 | 12/12 |
| tâches où SAT est strictement le meilleur | **2/6** | **7/12** |
| **regret médian** | 3,91 | **1,00** |
| **regret maximal** | **26,19×** | **14,46×** |
| temps total, politique | 0,173 s | 0,153 s |
| temps total, « toujours SAT » | 0,173 s | 0,153 s |
| temps total, `identity` seul | 2,989 s | 5,745 s |

## Ce que ces chiffres disent, et ne disent pas

**La politique n'est pas meilleure que la stratégie triviale.** Sur les deux groupes elle atteint
exactement le temps de « toujours SAT » (ratio 1,00). Plusieurs tâches, notamment les additionneurs
contrôlés, favorisent pourtant le symbolique ; la règle ne les identifie pas. Aucun avantage
du sélecteur n'est démontré sur des familles indépendantes.

**Elle est souvent nettement pire que le meilleur choix.** Le regret maximal est de **26,19×** sur
la sélection et **14,46×** sur le holdout, alors que les médianes sont de 3,91 et 1,00 : la médiane
cache des cas individuels très défavorables. Sur la sélection, SAT n'est optimal que sur **2 des 6**
tâches, et la politique le choisit pourtant partout.
Sur **cinq** des douze tâches, le symbolique est plus rapide que SAT, et de façon nette :

| tâche | SAT | meilleur symbolique | rapport |
|---|---:|---:|---:|
| `hold_cadder_11` | 8,50 ms | **1,42 ms** | 6,0× |
| `hold_cadder_13` | 13,00 ms | **5,48 ms** | 2,4× |

C'est le coût fixe de l'encodage, qui domine sous quelques millisecondes. Une règle qui choisirait
le symbolique sur ces deux cas aurait un meilleur regret — mais l'ajuster maintenant serait un
ajustement sur les données qui servent à le valider, ce que la mission interdit explicitement.

**Le « holdout » n'est pas un holdout d'architectures.** Il contient de nouvelles *tailles* de
générateurs déjà connus, plus deux incrémenteurs et trois chaînes MCX de tailles inédites. C'est une
extrapolation en taille, pas une généralisation à des familles indépendantes ni à des sorties de
compilateur.

## Ce qui reste utile, et à quel titre

1. **Les heuristiques d'ordre** sont mesurées et reproductibles : `last_use` est 58× plus rapide
   que `identity` sur les additionneurs, et 1,58× plus lent sur les chaînes MCX. Ce sont des
   options explicites, pas des défauts.
2. **La règle de repli** évite un échec : sans `python-sat`, la politique recommande le symbolique
   au lieu de sélectionner une méthode inexistante.
3. **La règle de moteur** n'a pas démontré sa valeur de sélection, mais elle documente un fait
   mesuré : au-delà de ~20 portes ou ~40 contrôles, le miter est linéaire en portes là où le coût
   symbolique croît sur les familles de monômes.

## Défaut conservé

`identity` et le moteur symbolique restent les comportements par défaut. La politique est une
fonction pure : rien dans le moteur ne change sans un appel explicite.

## Ce qu'il faudrait pour transformer cela en sélection démontrée

Un corpus **indépendant des familles ayant servi à établir les règles**, avec des réussites
contrastées des moteurs symbolique et SAT. Des gains symboliques existent déjà sur les additionneurs
contrôlés, mais la règle actuelle ne les anticipe pas. La conclusion demeure `EXPERIMENTAL` ;
toute nouvelle campagne confirmatoire relève des issues #44/#46, pas de cette PR.


## Campagne appariée finale (`RESULTS/paired_final.json`)

Protocole conforme à la demande : **un seul** appel `check_sat_equivalence`, `check_equivalence`
pour le ZDD, `backend_options={"collect_every": ...}` pour la collecte, même prédicat, même contrat
(équivalence fonctionnelle complète), mesure **externe** de l'appel entier, trois répétitions,
médianes. Budget : 30 s par appel, **coopératif (non préemptif)** pour tous les moteurs, plus 4 M nœuds
**pour le symbolique seulement** — le moteur SAT n'a pas de limite de nœuds équivalente.

Six tâches appariées :

| tâche | ZDD | ZDD + collecte | SAT |
|---|---:|---:|---:|
| `adder_12` | **1,6 ms** | 1,7 ms | 6,0 ms |
| `adder_16` | 31,0 ms | 30,8 ms | **12,0 ms** |
| `rand12x140_diff` | 3 096 ms | 2 598 ms | **11,7 ms** |
| `rand12x140_equiv` | 1 629 ms | 2 508 ms | **1 103 ms** |
| `rand14x160_diff` | budget | budget | **11,0 ms** |
| `rand14x160_equiv` | budget | budget | **2 057 ms** |

| moteur | décidées | temps total |
|---|---:|---:|
| ZDD natif | 4/6 | 4,68 s |
| ZDD + collecte | 4/6 | 5,17 s |
| **SAT (Glucose 4.2)** | **6/6** | 3,20 s |

**Aucun désaccord** entre les trois moteurs sur les tâches décidées. Le tableau est plus nuancé
que le résumé 17 tâches : SAT gagne massivement sur les circuits denses et les gros cas, mais perd
sur les petits additionneurs (`adder_12` : 6,0 ms contre 1,6 ms). C'est exactement la raison pour
laquelle une règle de sélection serait utile — et exactement ce que la règle actuelle ne fait pas,
puisqu'elle choisit SAT partout.

**Limite de provenance :** le JSON enregistre `git_head=04a2066c0fb5...` et
`worktree_dirty=true`. La version du solveur (`python-sat 1.9.dev17`), les limites et
les répétitions sont enregistrées, mais le code exact chargé **n'est pas identifié par
un instantané propre**. Ces résultats restent un pilote exploratoire, non une confirmation
sur le SHA final de #67 ou sur le futur `main`. Ne pas les attribuer à un autre SHA,
ni les utiliser comme argument de performance de publication.
