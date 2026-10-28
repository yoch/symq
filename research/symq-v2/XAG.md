# Encodeur XAG affine — résultat du pilote (issue #69)

**Décision : `STOP` pour l'encodage affine comme remplacement, `EXPERIMENTAL` pour le prototype
lui-même.**

L'hypothèse de l'issue était raisonnable : les circuits réversibles sont surtout linéaires, donc
représenter chaque fil comme une forme affine devrait réduire les variables intermédiaires. Le
prototype est correct et le démontre partiellement — mais le gain est réel sur une seule famille et
la régression est nette sur les autres.

## Ce qui est implémenté

`src/symq/sat/encoding_xag.py` : formulation intermédiaire (formes affines sur les entrées et les
nœuds AND), puis `src/symq/sat/miter_xag.py` : le miter, avec les mêmes trois verdicts, le même
`Contract`, le même choix de solveur (Glucose 4.2) et la même obligation de rejouer le témoin par
`Circuit.run` que l'encodeur de transition.

Aucun défaut par défaut n'est modifié : `check_sat_equivalence` reste l'entrée publique, et
`check_xag_equivalence` est une option explicite.

Deux bugs réels ont été trouvés et corrigés pendant la construction, tous deux détectés par les
tests différentiels :

1. l'encodeur allouait ses variables en réutilisant les numéros des entrées, si bien qu'un nœud AND
   et une entrée partageaient un numéro ;
2. les deux modèles (circuit gauche et droit) numérotaient leurs AND dans la même plage, donc un
   produit du circuit gauche et un produit du circuit droit étaient **la même variable**. Un
   circuit équivalent à lui-même était alors déclaré différent, et inversement.

Le second est instructif : une erreur de nommage de variables produit exactement le symptôme d'un
encodage « incomplet », et seuls les tests contre l'exécution exhaustive l'ont révélée.

## Exactitude

- `tests/test_xag_equivalence.py` : **73 tests**, dont 40 différentiels contre l'exécution concrète
  sur toutes les entrées, et 25 comparant les deux encodeurs sur la même instance.
- Vérification supplémentaire sur 30 circuits aléatoires : **30/30** d'accord avec l'exécution
  exhaustive.
- Aucun désaccord entre les deux encodeurs sur les 10 cas du pilote.

L'exactitude est donc établie sur les petites largeurs, ce qui est la condition d'acceptation de
l'issue.

## Premier pilote (historique ; ne pas confondre avec la répétition propre)

| tâche | SSA ms | XAG ms | ratio | variables | clauses |
|---|---:|---:|---:|---:|---:|
| `gf12_mul` | 42,37 | 42,92 | 0,99 | 720 → 720 | 2305 → 2305 |
| `gf12_mul_mutant` | 1,70 | 13,58 | **0,12** | 720 → 718 | 2303 → 2298 |
| `adder_8` | 3,20 | 4,35 | 0,74 | 184 → 166 | 597 → 541 |
| `adder_8_mutant` | 1,25 | 0,73 | 1,71 | 186 → 166 | 602 → 541 |
| `adder_12` | 6,01 | 5,65 | 1,06 | 272 → 246 | 885 → 805 |
| `adder_12_mutant` | 3,67 | 1,73 | **2,11** | 275 → 258 | 895 → 850 |
| `rand10x120_diff` | 56,17 | 57,58 | 0,98 | 534 → **858** | 1668 → **3189** |
| `rand10x120_equiv` | 657,57 | 196,32 | **3,35** | 532 → 858 | 1663 → 3189 |
| `rand12x160_diff` | 11,23 | 20,30 | 0,55 | 708 → **1376** | 2266 → **5162** |
| `rand12x160_equiv` | 556,95 | 1636,28 | **0,34** | 712 → 1361 | 2281 → 5099 |

**Premier pilote : geomean SSA/XAG = 0,86, XAG gagne 4/10.** La campagne corrigée sur arbre propre (`RESULTS/xag_pilot.json`, `git_head=cb1bf8a62059e6db703dee5b6a6e2785736d18d4`, Glucose 4.2 / python-sat 1.9.dev17) donne **0,839**, XAG gagnant **4/10** et aucun désaccord. Les tableaux historiques sont conservés, mais seul le JSON actualisé contient les durées de la deuxième campagne.

## Ce que les chiffres disent

**Le CNF n'est pas plus petit sur les circuits denses, il est plus gros.** Sur `rand10x120`,
l'encodeur affine alloue **858 variables contre 534** et **3 189 clauses contre 1 668**. La raison
est structurelle : une forme affine de support `k` coûte `k - 1` variables auxiliaires pour sa
chaîne XOR, et les circuits denses ont des supports larges. Les 40 portes CX d'un circuit dense
produisent donc de longues chaînes, exactement le risque que l'issue anticipait.

**Les additionneurs sont le cas favorable, et le gain y est modeste** : −7 % de variables et −9 % de
clauses sur `adder_12`, avec un temps presque identique (1,06). Sur le mutant, XAG est 2,11× plus
rapide, ce qui suggère que la représentation aide surtout quand le solveur peut conclure vite sur une
structure linéaire.

**Le cas `gf12_mul` est neutre par construction** : le bloc est un réseau de CCX sans couche
linéaire significative, donc les deux encodeurs produisent le même nombre de variables (720). Ce
n'est pas une validation de l'hypothèse, c'est sa réfutation sur ce cas.

**Aucune famille ne montre de gain indépendant de la famille.** Le seul ratio supérieur à 3 est un
cas équivalent difficile, et le cas symétrique (`rand12x160_equiv`) donne 0,34 — l'écart va dans les
deux sens sur la même famille, ce qui interdit de conclure à un avantage structurel.

## Limites

- **Le fixture qant n'a pas été utilisé dans ce benchmark.** L'environnement de l'agent n'avait pas accès au dépôt **privé** `yoch/qant` (404). `gf12_mul_block` est une construction scolaire locale non réduite, de 48 fils / 144 CCX, et ne représente pas le bloc qualifié de qant. Ne pas copier des sources privées dans le dépôt public sans autorisation explicite.
- Le pilote inclut jusqu'à **48 fils** (construction GF12 scolaire), mais ne constitue pas une validation du multiplicateur GF12 réel de qant.
- Trois répétitions par cellule : suffisant pour un pilote, pas pour une campagne confirmatoire.
- Aucun paramètre n'a été ajusté sur ces cas, mais la famille a été choisie après avoir vu que les
  additionneurs sont linéaires.

## Décision

**`STOP`** sur l'idée que l'encodage affine réduit le CNF de façon générale : c'est faux sur les
circuits denses, où il l'agrandit de 60 à 130 %.

**`EXPERIMENTAL`** pour le prototype : il est correct, testé, et il documente précisément *quand* la
représentation aide — circuits à forte composante linéaire et faible support, typiquement les
additionneurs — et quand elle nuit — circuits denses à large support.

Ne pas construire d'optimiseur XAG général. Ne pas ajouter CryptoMiniSat : la comparaison de
contraintes XOR natives ne se justifie que si la représentation gagne d'abord, ce qui n'est pas le
cas.

## Suite après revue et diagnostic #70

- **Priorité #71 :** les contrats relationnels permettent de poser de nouvelles obligations réelles, au lieu de modifier uniquement leur encodage.
- **#70 : STOP sur le COI en équivalence complète** (aucune porte élagable par construction), et aucun investissement immédiat pour le partage de préfixes sans preuve de gain sur une paire réellement difficile. Un préfixe commun de 89 % ne démontre pas une accélération ; il n'est cependant pas invalidé par la mesure de COI.
- **#69 :** le prototype reste expérimental sur sa branche ; aucun remplacement général de SSA. Le pilote propre mesure un encodage XAG plus lent à construire, par exemple ~12,2 ms contre ~0,67 ms pour SSA sur la multiplication scolaire.

### Correctif du contrôle temporel

Le commit `95b186225e6bb90745ffd23ab00667bf153f7cb4` rétablit le début de l'horloge **avant** la construction CNF pour SSA et XAG, avec des tests de ralentissement artificiel des encodages, d'UNSAT tardif et de décompte de l'extraction/relecture du témoin. Ne pas utiliser la refactorisation du pilote comme argument pour rendre XAG productif.
