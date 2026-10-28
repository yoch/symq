# XAG et synthèse réversible — artefact GF(2ⁿ) : borne d'incidences, trois constructions exactes, cible bloquée

**Trois conclusions distinctes, à ne pas confondre :**

| verdict | objet |
|---|---|
| **`VALIDATED`** | la borne d'incidences bilinéaires `Σ_s popcount(w_s) ≥ n²`, et la correction exacte des trois constructions émises |
| **`NEGATIVE`** | absence de gain des stratégies particulières **réellement évaluées** ici : trois décompositions, un émetteur par terme, 300 bases aléatoires |
| **`BLOCKED`** | l'optimisation du circuit qant 42 CCX / 433 CX, faute d'accès aux données dans cet environnement |

Aucune optimalité n'est affirmée. Aucune nouveauté mathématique n'est revendiquée. Aucun gain de
score quantique n'est mesuré ni annoncé.

---

## 1. Statut de la cible : `BLOCKED` par les permissions

Le dépôt `yoch/qant` est privé et son accès ne se transmet pas automatiquement entre agents. Dans cet
environnement il répond 404 sur le dépôt, sur le commit `071f8c80…` et sur chacun des quatre fichiers
de référence ; aucune copie locale n'existe. Les fichiers suivants n'ont **jamais été lus** :

```
src/qant/blocks/gf12_stateful.py
experiments/blocks/gf12_stateful_20261028/audit/{candidate,witness,mutant-drop-ccx}.json
```

Ce blocage est une **limite de permissions**, pas une preuve que le circuit est non optimisable. Aucun
chiffre de qant n'apparaît dans ce document, et aucun fixture privé n'est copié ici — y compris si
l'accès devenait disponible : la reprise se ferait dans qant, pas dans ce dépôt public.

Ce qui suit porte donc sur la **fonction** `(a,b,z) ↦ (a,b,z ⊕ ab)` dans GF(2¹²) mod `0x1053`, que le
cahier des charges spécifie complètement.

---

## 2. `VALIDATED` — la borne d'incidences

### Énoncé, avec son domaine de validité

Soit la multiplication dans GF(2ⁿ) vue comme un tenseur `T` sur GF(2) avec `T[i][j] = xⁱ·xʲ`. Une
**décomposition bilinéaire en termes de rang un**, dans un ensemble fixé de coordonnées de sortie,
s'écrit

$$T = \sum_{s=1}^{r} u_s \otimes v_s \otimes w_s,$$

chaque terme produisant `(u_s·a)(v_s·b)` et l'accumulant dans les coordonnées nommées par `w_s`. Alors

$$\sum_s \operatorname{popcount}(w_s) \;\ge\; \sum_k \operatorname{rank}(A_k) \;=\; n^2,$$

où `A_k[i][j]` est le bit `k` de `T[i][j]`.

**Ce que cela signifie exactement** : toute décomposition en termes de rang un, dans ces coordonnées
de sortie, dépense au moins `n²` incidences (terme, bit d'accumulateur). Ni plus, ni moins.

### La preuve

**Fait 1 (rang d'une forme bilinéaire non nulle).** `A_k` est la matrice de la forme `B_k(a,b) = aᵀA_kb`
dans la base canonique. Écrire `B_k` comme somme de `t` termes `u_t ⊗ v_t` exige `t ≥ rank(A_k)`,
puisque chaque terme apporte une matrice de rang un `u_t v_tᵀ` et que le rang est sous-additif.

**Fait 2 (non-dégénérescence de chaque tranche).** GF(2ⁿ) est un **corps** : tout `a ≠ 0` est
inversible, donc `b ↦ a·b` est une bijection, et `a·b ≠ 0` dès que `a ≠ 0` et `b ≠ 0`. La forme
coordonnée `B_k` n'est donc pas identiquement nulle.

**Le rang vaut exactement `n`.** `A_k[i][j]` est le coefficient de `xᵏ` dans `xⁱ·xʲ`. Supposons
`Σᵢ cᵢ B_k(xⁱ, b) = 0` pour tout `b`, c'est-à-dire que le bit `k` de `(Σᵢ cᵢxⁱ)·b` est identiquement
nul. Par le fait 2, cela force `Σᵢ cᵢxⁱ = 0`, donc tous les `cᵢ = 0`. Les `n` lignes de `A_k` sont
linéairement indépendantes : `rank(A_k) = n`.

**Conclusion.** Notons `c_k` le nombre de termes dont le support `w_s` contient `k`. Chaque terme
apporte au plus une pièce de rang un à la coordonnée `k`, donc `c_k ≥ rank(A_k) = n`. En sommant sur
les `n` coordonnées :

$$\sum_s \operatorname{popcount}(w_s) = \sum_k c_k \;\ge\; \sum_k \operatorname{rank}(A_k) = n^2.$$

Le théorème repose sur cet argument, pas sur l'accord entre deux programmes. `rank_gaussian` et
`rank_incremental` sont deux **vérifications croisées** qui garantissent que les tables calculées ne
contiennent pas d'erreur de codage, et `budget()` lève si elles divergent.

| n | rangs par coordonnée | plancher `Σ|w|` | schoolbook `Σ|w|` | marge |
|---:|---|---:|---:|---:|
| 2 | (2,2) | 4 | 5 | 1 |
| 3 | (3,3,3) | 9 | 12 | 3 |
| 4 | (4,4,4,4) | 16 | 22 | 6 |
| 8 | (8,…,8) | 64 | 151 | 87 |
| **12** | **(12,…,12)** | **144** | **363** | **219** |

Le plancher est **atteint** par la construction « plancher de rang » (144 incidences à n = 12), ce qui
montre que la borne est serrée pour cette décomposition.

### Ce que cette borne n'est pas

Ce n'est **pas** une borne sur les portes CCX, CX ou T, ni sur la taille d'un programme réversible
quelconque. Un programme réversible peut calculer des fonctions intermédiaires qui ne sont pas des
termes bilinéaires de rang un, changer de base linéaire entre deux produits, et réutiliser ou
désaccumuler des fils ; rien de tout cela n'est compté par `Σ_s popcount(w_s)`.

Le test `test_the_bound_is_not_a_gate_bound` exhibe un programme de **trois** portes qui livre **deux**
incidences sur un fil à l'aide d'un seul CX (le CX recopie le bit entier, junk compris). Tout argument
qui promouvrait la borne en borne de portes devrait expliquer pourquoi ce programme est impossible ; il
ne l'est pas.

---

## 3. `VALIDATED` — trois constructions exactes

Trois décompositions de la même fonction, émises sur 36 fils, sans ancilla, et prouvées exactes par
ANF (section 5). Les coûts sont donnés **par axe** ; aucun total de portes non pondéré n'est utilisé
pour les classer, car un Toffoli et un CNOT ne sont pas interchangeables.

| décomposition | termes | incidences | CCX | CX | fils | profondeur |
|---|---:|---:|---:|---:|---:|---:|
| schoolbook | 144 | 363 | 363 | 0 | 36 | 321 |
| Karatsuba | 54 | 313 | 313 | 424 | 36 | 326 |
| plancher de rang | 144 | 144 | 144 | 438 | 36 | 380 |

Lecture honnête de ce tableau — les trois points sont **Pareto-incomparables** sur
`(CCX, CX, fils, profondeur)` : aucun ne domine les autres, et aucun ne les domine tous.

- **schoolbook** minimise les CX (zéro) et la profondeur, mais maximise les CCX et les incidences ;
- **plancher de rang** minimise les CCX (144) et atteint le plancher d'incidences, mais maximise les
  CX et la profondeur ;
- **Karatsuba** est intermédiaire : moins de CCX que schoolbook (313 contre 363) et moins de CX que le
  plancher de rang (424 contre 438), mais il ne gagne sur aucun axe de façon décisive et il perd sur
  la profondeur face à schoolbook.

Aucune de ces trois constructions n'est comparable au circuit qant 42 CCX / 433 CX : ce dernier n'a
jamais été lu. Il n'est donc pas possible de dire qu'elles sont « pires » ou « meilleures » que lui, et
le tableau ne permet pas de conclure à une supériorité d'une architecture sur une autre.

---

## 4. `NEGATIVE` — portée exacte des résultats négatifs

### Ce que l'émetteur fait réellement

`emit()` applique, **pour chaque terme**, le schéma repli / CCX / dépli :

```
pour chaque terme :  repli(u)  (p−1 CX) ; un CCX par bit d'accumulateur ; dépli(u)  (p−1 CX)
```

Chaque terme repart donc de la base d'origine. **Ce n'est pas une recherche d'ordonnancement à bases
linéaires persistantes.** Un synthétiseur à état conserve les bases modifiées entre produits
consécutifs, si bien que deux formes *distinctes* peuvent partager une transformation linéaire
intermédiaire ; rien ici n'explore cela. Le coût de transition entre formes voisines et les
factorisations partielles ne sont pas modélisés non plus.

### Résultat négatif n°1 : le partage de formes identiques, sur ces jeux de termes

`emit(..., share=True)` regroupe les termes dont la paire `(left, right)` est **exactement identique**
et ne replie cette paire qu'une fois. C'est une hypothèse étroite : formes identiques répétées, et
rien d'autre.

Sur les trois jeux de termes mesurés, la multiplicité maximale d'une paire `(left, right)` vaut **1**.
Le regroupement ne peut donc rien économiser *sur ces jeux-là*. Cela ne dit rien des formes qui se
chevauchent, du partage partiel, ni de la réutilisation d'un état de base entre produits distincts.

Le compte glouton `2·(popcount(sx)−1) + (popcount(sz)−1)` surestime le coût de repli de ces jeux de
termes (683 contre 424 CX mesurés à n = 12 pour Karatsuba), mais cette surestimation est une propriété
de ce comptage, pas une preuve qu'un autre ordonnancement serait inutile.

### Résultat négatif n°2 : 300 bases aléatoires

J'ai essayé 300 changements de base inversibles aléatoires sur `a`, en mesurant le poids total des
formes (donc le coût de repli). Aucun n'améliore la base d'origine ; le meilleur obtenu donne un poids
total de 216 contre 106 dans la base naturelle.

**Énoncé exact** : aucune des 300 bases aléatoires essayées n'améliore cette fonction de coût sur cette
décomposition. Cela n'établit ni l'optimalité de la base naturelle, ni l'absence d'espoir pour des
bases structurées, des mises à jour d'état conjointes, ou un ordonnancement.

### Ce qui n'a pas été testé

| piste | statut |
|---|---|
| ordonnancement global à bases persistantes sur le circuit réel | **non testé** — nécessite le générateur qant |
| réécritures XAG locales (axe B) | **non testées** — aucune structure réelle à cibler |
| synthèse linéaire PMH (axe C) | **non testée** — ne s'applique qu'aux transformations du bloc réel |
| autres jeux de termes à 42 termes | **non testés** |

Il n'y a donc **aucun `STOP` général sur l'ordonnancement global** : cet algorithme n'a pas été
implémenté sur le véritable circuit, et la question reste ouverte.

---

## 5. Vérification : ce qui est prouvé, et comment

**Énumération exhaustive (n ≤ 5).** Les `2^(3n)` affectations de `(a, b, z)` sont parcourues : `a` et
`b` restaurés, `z` accumule exactement le produit, aucun fil auxiliaire. Zéro échec sur les neuf
circuits.

**Preuve symbolique (toutes largeurs, dont n = 12).** GF(2¹²) a `2³⁶` entrées, donc l'énumération est
impossible. `proof.py` construit l'ANF attendue de chaque fil de sortie par **deux constructions
indépendantes** — depuis la table de corps, et depuis le jeu de termes de l'émetteur — vérifie qu'elles
coïncident, puis compare fil par fil aux ANF simulées du circuit. Les ANF étant canoniques, l'égalité
fil par fil **est** l'équivalence fonctionnelle sur les `2³⁶` entrées.

`gf_mul` est recoupé contre l'implémentation indépendante de l'archive du 27 octobre
(`research/archive/2026-10-27/src/field_phase.py`, même modulus) sur un ensemble déterministe
d'opérandes, et l'irréductibilité de chaque modulus est vérifiée par division exhaustive. Les
opérandes hors du corps (`≥ 2ⁿ`) **lèvent une erreur** au lieu d'être tronqués silencieusement — le
bug que ce resserrage a effectivement attrapé dans mes propres tests.

**Mutants rejoués à n = 12** — le vérificateur doit refuser une transformation incorrecte :

| mutant | verdict |
|---|---|
| CCX supprimée | **DIFFERS**, fil 25 |
| contrôles échangés | **DIFFERS**, fil 25 |
| fan-out sur `z` sale | **DIFFERS**, fils 25–35 |
| jeu de termes corrompu | rejeté à l'assertion d'identité tensorielle |

Aucun certificat n'est transféré d'un circuit à un autre : chaque candidat est prouvé sur son propre
contenu.

**Portée de ces preuves** : elles établissent que les circuits émis calculent bien leur fonction
classique. Elles ne disent rien d'une optimisation du circuit qant.

---

## 6. Coût quantique : non mesuré

Aucun émetteur Clifford+T n'a été écrit, donc **aucun T-count n'est mesuré ni revendiqué** pour un
candidat. Le cahier des charges demandait explicitement de ne pas confondre coût réversible et coût
quantique ; ce document s'y tient.

Une seule remarque arithmétique, présentée comme telle et non comme une mesure : dans le jeu standard,
CNOT est Clifford (0 T) et Toffoli vaut 7 T. Une réduction de CX n'achète donc aucun T, tandis qu'une
CCX en moins en vaut 7. La constante 4T/AND de Meuli–Soeken–De Micheli suppose un qubit initialisé à
|0⟩, ce que ce bloc (zéro scratch, `z` sale) n'offre pas. **Aucun score n'est prédit à partir de là.**

---

## 7. Ce qui est réutilisable

1. **La borne d'incidences**, prouvée pour tout corps et tout modulus irréductible, avec son domaine de
   validité explicite. C'est un filtre de recherche : il élimine les jeux de termes qui prétendraient
   dépenser moins de `n²` incidences.
2. **Le harnais de preuve ANF** (`proof.py`), indépendant de tout fichier qant, qui rend un candidat
   GF(2¹²) vérifiable sans énumération.
3. **Trois constructions exactes** et leurs coûts par axe, comme points de comparaison reproductibles.
4. **Les tests de mutants**, qui garantissent que le vérificateur refuse réellement ce qu'il doit
   refuser.

## 8. Ce qu'il faudrait pour reprendre la cible

L'accès en lecture à `yoch/qant` dans un environnement autorisé, et les quatre fichiers listés en §1.
La reprise se ferait **dans qant**, pas ici. Le harnais `proof.py` est portable tel quel.

---

## 9. Provenance et reproduction

- Base : `yoch/symq` `main` = `6c4d20a6b0cfb83fe9ecb836ecf8cf5dae9d495c` (« Merge #76 »).
- Branche : `explore/xag-reversible-synthesis-20261028`.
- Python 3.12.3, pytest 9.1.1, ruff 0.17.3. Aucune dépendance nouvelle.

```
PYTHONPATH=src /tmp/venv/bin/python research/xag-synthesis/tensor_budget.py
PYTHONPATH=src:research/xag-synthesis /tmp/venv/bin/python research/xag-synthesis/decompositions.py
PYTHONPATH=src:research/xag-synthesis /tmp/venv/bin/python research/xag-synthesis/proof.py
/tmp/venv/bin/python -m pytest tests/test_xag_decompositions.py -q      # 77 passed, ~8 s
/tmp/venv/bin/ruff check research/xag-synthesis tests/test_xag_decompositions.py
```

Les campagnes exhaustives `2^24` ont été remplacées par des couvertures déterministes plus ciblées
(opérandes à un seul bit exhaustifs, qui sont exactement les entrées du tenseur, plus un ensemble
d'extrêmes), ce qui ramène la suite de 89 s à 8 s sans perdre la vérification du tenseur. La preuve
algébrique de la borne remplace l'accord entre programmes comme argument principal.

Empreintes des fichiers de cette révision :

```
research/xag-synthesis/tensor_budget.py    e59b911b2052df25e337ad497619a94fa1b2854ac50a0953b59284429c883574
research/xag-synthesis/decompositions.py   01d61bd65fed50c7227945546f015b51a250a456d7daa153b4839f2b029eb56c
research/xag-synthesis/proof.py            5cebef197eb55a1e904af5c752303ff88566098e0d9496ee78fd77059e56115c
tests/test_xag_decompositions.py           442c025c93d6bd2e8e6ec90602e9cf98addb30c3388f124b316733bef4f2b215
```
