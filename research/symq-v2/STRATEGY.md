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
| **regret médian** | 1,00 | **1,00** |
| accélération contre le défaut (`identity` + symbolique) | — | **1,81×** |

Le regret est le rapport entre le temps de la politique et celui du meilleur choix *mesuré* : 1,00
signifie que la politique atteint toujours l'optimum disponible, sans l'avoir mesuré.

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
