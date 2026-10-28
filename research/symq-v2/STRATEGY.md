# Stratégie automatique — ordre et moteur, avec validation hors échantillon

## Les deux décisions sont séparées

Choisir un ordre pour un backend déjà choisi et choisir un moteur pour une tâche ne demandent pas
les mêmes indices. Les deux sont implémentés dans `src/symq/strategy.py`, chacun avec sa règle
énoncée en clair.

## Les caractéristiques, et pourquoi celles-là

Une seule passe sur la liste de portes, aucun essai de simulation :

| feature | ce qu'elle capte |
|---|---|
| `last_use_spread` | écart-type des positions de dernier usage, normalisé. Proche de 0 : tous les fils finissent ensemble (cascade). Grand : structure étagée. |
| `distinct_controls` | nombre de fils utilisés comme contrôle |
| `mean_arity` | contrôles par porte : bas = structure de registres, haut = portes larges |
| `depth_estimate` | longueur de la plus longue chaîne de portes partageant un fil |
| `width`, `gates`, `used_wires`, `max_arity`, `first_use_spread` | taille et forme |

Mesuré sur les familles connues :

| famille | `last_use_spread` | `mean_arity` | ordre choisi |
|---|---:|---:|---|
| additionneurs Cuccaro (8-19 bits) | 0,150-0,156 | 1,33 | **`last_use`** |
| additionneurs contrôlés | 0,156-0,160 | 2,33 | **`last_use`** |
| chaînes MCX | 0,000 | 6,0-10,0 | `identity` |
| incrémenteurs | 0,288 | 5,5-7,5 | `identity` |
| circuits denses | 0,015-0,061 | 1,1-1,6 | `identity`, puis SAT si assez grands |

## Les règles

```
ordre   : last_use  si spread >= 0.12 et distinct_controls >= 3 et gates >= 24
          reversed  si spread >= 0.12 et gates >= 24
          identity  sinon
moteur  : sat       si python-sat installé et width >= 12 et gates >= 120 et mean_arity <= 2.5
          symbolic sinon
```

Aucune règle ne lit le nom du circuit ni la position d'un fil pour deviner une sémantique
arithmétique : tout vient de la forme de la liste de portes.

## Validation, protocole fixé avant la mesure

- **sélection** : 6 tâches déjà vues dans les campagnes précédentes ;
- **holdout** : **12 tâches** de familles absentes de la sélection — tailles d'additionneurs
  inédites (15, 17, 19 bits), additionneurs contrôlés (11, 13), incrémenteurs (12, 16), chaînes MCX
  (12, 16, 20), circuits denses (15×180, 17×220).

Résultats (`RESULTS/strategy_pilot.json`) :

| mesure | sélection | holdout |
|---|---:|---:|
| tâches résolues par la politique | 6/6 | **12/12** |
| résolues par `identity` seul | 5/6 | 10/12 |
| résolues par `reversed` seul | 5/6 | 10/12 |
| résolues par `last_use` seul | 5/6 | 10/12 |
| résolues par SAT seul | 6/6 | 12/12 |
| temps total de la politique | 0,173 s | **0,153 s** |
| temps total de « toujours SAT » | 0,173 s | 0,153 s |
| temps total de « toujours identity » | 2,989 s | 5,745 s |
| **regret médian** | 3,91 | **1,00** |

Le regret est le rapport entre le temps de la politique et celui du meilleur choix *mesuré* :
1,00 signifie que la politique atteint l'optimum disponible sans l'avoir mesuré.

**Ce que la première version annonçait, et pourquoi c'était faux.** Elle rapportait un regret
médian de 1,00 en prenant le minimum des **trois ordres symboliques** seulement : SAT était exclu
du calcul, donc la politique paraissait optimale par construction. Recalculé avec tous les moteurs,
le regret médian était **1,67** et le maximum **81×**. La conséquence était plus grave que le
chiffre : la politique choisissait parfois le symbolique là où SAT était 65× plus rapide, et elle
était **12× plus lente que « toujours SAT »** sur le holdout (0,929 s contre 0,075 s).

**La règle a donc été refaite sur les données, pas ajustée pour sauver le chiffre :**

```
moteur : sat si le solveur est disponible et (gates >= 20 ou controls_total >= 40)
         sinon symbolic
```

Deux règles antérieures ont été essayées et **rejetées par les mêmes données**, ce qui est consigné
dans le module :

| règle essayée | pourquoi elle échoue |
|---|---|
| `mean_arity <= 2.5` | exclut les additionneurs (arité 1,33) et les chaînes MCX (arité 10), les deux familles où SAT gagne de 3× à 75× |
| `gates >= 20` seule | manque une chaîne MCX de 19 portes et 190 contrôles : 135 ms en symbolique contre 2 ms en SAT |

**Mesures refaites avec Glucose 4.2** (le solveur par défaut depuis la correction de
l'interruption). Deux changements notables par rapport aux chiffres CaDiCaL :

- le regret médian de **sélection** passe de 2,05 à **3,91** : Glucose paie un coût d'encodage plus
  élevé sur les petits circuits, donc choisir le symbolique y est plus souvent payant ;
- le temps total double (0,075 s → 0,153 s sur le holdout), pour la même raison.

La politique atteint toujours **exactement** « toujours SAT » (ratio 1,00 sur les deux groupes),
mais elle ne le dépasse pas, et son intérêt réel se limite à deux cas : une installation sans
solveur retombe proprement sur le symbolique, et les circuits sous la milliseconde évitent le coût
fixe de l'encodage. Ce n'est pas une sélection supérieure, et le rapport ne le prétend plus.

Sur le corpus mesuré, la règle choisit SAT partout : elle **reproduit** la stratégie triviale au
lieu de la battre. Une vraie sélection demanderait un corpus où le symbolique gagne sur des
circuits non triviaux, ce que les 12 tâches du holdout ne contiennent pas.

## Ce que cette validation ne prouve pas

- Le holdout contient des **tailles inédites de générateurs connus**, pas des architectures
  indépendantes. C'est une extrapolation, pas une généralisation à des sorties de compilateur.
- Aucune comparaison à un réordonnancement dynamique de CUDD n'est faite ici.
- Le coût d'extraction des features est mesuré (moins de 10 ms pour 400 portes, test
  `test_selection_cost_is_negligible`) mais n'est pas inclus dans le total ci-dessus, où il est
  négligeable devant les temps de vérification (millisecondes à secondes).
- `last_use` reste **non universel** : la règle l'exclut explicitement des cascades, où il coûte
  1,58×.

## Défaut conservé

`identity` et le moteur symbolique restent les comportements par défaut. La politique est une
fonction purement additive : rien dans le moteur ne change de comportement sans un appel explicite.
