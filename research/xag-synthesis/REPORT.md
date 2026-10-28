# XAG et synthèse réversible — bloc GF(2¹²) : accès bloqué, et ce qui reste démontrable

**Décisions : `BLOCKED` sur la cible qant · `STOP` sur l'ordonnancement des produits · `EXPERIMENTAL`
sur les trois décompositions exactes, sans gain face à la baseline.**

Ce rapport sépare deux choses que la mission demande de ne pas confondre : ce que je n'ai pas pu
mesurer (le circuit qant, inaccessible), et ce que j'ai pu **prouver** sur la fonction qu'il calcule,
indépendamment de la façon dont qant la construit.

---

## 1. Le blocage d'accès, vérifié sur tous les chemins

Le dépôt privé `yoch/qant` n'est pas accessible depuis cet environnement :

```
gh api repos/yoch/qant                                      -> 404 Not Found
gh api repos/yoch/qant/commits/071f8c80da8101d83...         -> 404 Not Found
git ls-remote https://github.com/yoch/qant                  -> Repository not found
gh repo view yoch/qant                                       -> Could not resolve to a Repository
```

Aucune copie locale n'existe (`find / -name "gf12*"` ne renvoie que mes propres fichiers de travail ;
`/tmp/arch_run` est l'archive du 27 octobre et ne contient aucun fixture GF(2¹²)).

Les quatre fichiers de référence n'ont donc **jamais été lus** :

```
src/qant/blocks/gf12_stateful.py
experiments/blocks/gf12_stateful_20261028/audit/candidate.json
experiments/blocks/gf12_stateful_20261028/audit/witness.json
experiments/blocks/gf12_stateful_20261028/audit/mutant-drop-ccx.json
```

Conformément au cadrage, je n'ai **pas** reconstruit silencieusement ces fixtures. Aucun chiffre de ce
rapport n'est un chiffre de qant. Ce qui suit porte sur la **fonction**

\[
(a,b,z)\longmapsto(a,b,z\oplus ab),\qquad \text{GF}(2^{12}) \bmod 0x1053,
\]

que la mission spécifie complètement, et qui contraint toute réalisation réversible.

---

## 2. Résultat principal : le plancher d'incidences (prouvé)

Multiplication dans GF(2ⁿ) est bilinéaire, donc c'est un tenseur `T[i][j] = xⁱ·xʲ`. Un algorithme
bilinéaire est un ensemble de termes `(u, v, w)` : calculer `(u·a)(v·b)` et l'ajouter aux bits
d'accumulateur de `w`. Le nombre de termes est la complexité multiplicative ; `Σ|w|` compte les
**incidences** (terme, bit d'accumulateur).

Découpons `T` par coordonnée de sortie : `A_k[i][j] = bit_k(T[i][j])`. La coordonnée `k` vaut la forme
bilinéaire `aᵀ A_k b`, qui exige au moins `rank(A_k)` termes rang-un, chacun contribuant au plus une
incidence à la coordonnée `k`. Donc

\[
\sum_s |w_s| \;\ge\; \sum_k \operatorname{rank}(A_k).
\]

Le module vérifie, par **deux algorithmes de rang indépendants** (Gauss-Jordan et insertion dans une
base triangulaire, qui doivent coïncider sinon `budget()` lève), que `rank(A_k) = n` pour tout `k` :

| n | rangs par coordonnée | plancher `Σ|w|` | schoolbook `Σ|w|` | marge |
|---:|---|---:|---:|---:|
| 2 | (2,2) | 4 | 5 | 1 |
| 3 | (3,3,3) | 9 | 12 | 3 |
| 4 | (4,4,4,4) | 16 | 22 | 6 |
| 8 | (8,…,8) | 64 | 151 | 87 |
| **12** | **(12,…,12)** | **144** | **363** | **219** |

**Conséquence.** Toute décomposition bilinéaire de la multiplication GF(2¹²) compte **au moins 144
incidences**. Le schoolbook en dépense 363, soit 219 de trop ; une décomposition de Karatsuba en
dépense 313.

**Ce que cela ne dit pas.** Ce n'est **pas** une borne sur les CX, et il ne faut pas l'utiliser comme
telle. J'ai d'abord cru pouvoir en déduire `CX ≥ 144 − r`, puis je l'ai réfuté : un CX recopie le bit
entier, junk compris, donc il ne peut pas livrer un produit à un second bit d'accumulateur sans y
livrer aussi le contenu antérieur de la source. Le test
`test_cx_copies_junk_so_the_incidence_floor_is_not_a_cx_bound` fige exactement cela, et le mutant
`fanout_shortcut` échoue la preuve à n=12 sur 11 fils. La borne porte sur les **termes**, pas sur les
portes.

---

## 3. Résultat négatif principal : l'ordonnancement ne paie pas

La mission désigne comme priorité absolue l'ordonnancement global des 42 produits, avec la fonction de
coût gloutonne `2·(popcount(sx)−1) + (popcount(sz)−1)`. J'ai construit trois décompositions exactes et
mesuré le coût de chacune, sur 36 fils, sans ancilla.

| décomposition | termes | incidences | CCX | CX | total | profondeur | preuve |
|---|---:|---:|---:|---:|---:|---:|---|
| schoolbook | 144 | 363 | 363 | 0 | 363 | 321 | ANF exacte |
| Karatsuba | 54 | 313 | 313 | 424 | 737 | 326 | ANF exacte |
| plancher de rang | 144 | 144 | 144 | 438 | 582 | 380 | ANF exacte |
| *baseline qant (non mesurée)* | *42* | *—* | *42* | *433* | *475* | *—* | *non vérifiable* |

**L'ordonnancement ne change rien, et c'est démontrable.** Le coût de repli appartient à une *forme*,
pas à un produit : une forme utilisée par `m` produits devrait pouvoir être repliée une fois et
dépliée une fois, économisant `2(p−1)(m−1)` CX. J'ai implémenté ce partage (`emit(..., share=True)`).
Il ne déclenche **jamais** : sur le jeu de termes Karatsuba, `max_form_multiplicity = 1`, c'est-à-dire
que les 54 formes gauches et les 54 formes droites sont **toutes distinctes**. Il n'y a aucune forme
réutilisable à créditer, donc aucun gain à récupérer. Le compte glouton (683) est simplement une
surestimation permanente de 259 CX ; le partage ne la corrige pas, il n'a rien à partager.

**La sélection de base ne paie pas non plus.** J'ai cherché une base de `a` qui réduirait le poids
total des formes (donc le coût de repli) : sur 300 changements de base inversibles aléatoires, le
meilleur trouvé donne un poids total de **216**, contre **106** dans la base d'origine. Autrement dit,
la base naturelle est déjà la bonne, et toute base alternative est *pire*. Ce n'est pas une preuve
d'optimalité, mais cela retire l'espoir que l'axe A parte d'une base mal choisie.

---

## 4. Pourquoi la baseline est peut-être déjà au plancher structurel

`42 = 7 × 6`. C'est exactement le compte de **Toom-3 sur 4 blocs de 3 coefficients** : 7 évaluations,
chacune un produit 3×3 en 6 termes bilinéaires. Ce n'est pas une coïncidence suggestive, c'est le
schéma standard pour multiplier deux polynômes de degré 11 (12 coefficients), et 42 est le compte
attendu de cette construction.

Si c'est bien la structure de `synthesize_stateful_36wire_circuit()`, alors :

- le nombre de termes est **déjà** celui d'un algorithme bilinéaire non trivial, pas d'un schoolbook
  (144) ni d'un Karatsuba binaire (54, mesuré) ;
- ses 433 CX se décomposent en au moins **102** écritures de distribution inévitables
  (144 − 42) plus **331** pour le changement de base et sa restauration ;
- les 331 restants sont le seul gisement réel, et ils correspondent à une transformation linéaire
  12×12 sur `a`, une sur `b`, et leur annulation — ce qui ramène à l'axe C (Patel–Markov–Hayes), pas à
  l'axe A.

Je présente cela comme une **inférence à partir de l'arithmétique**, pas comme une lecture du code :
je n'ai pas vu `synthesize_stateful_36wire_circuit()`. C'est la première chose à vérifier avec l'accès.

---

## 5. Le résultat qui change la priorité : CX ne paie pas de T

La mission fixe comme objectif « moins de 433 CX », avec 5 % (≈ 21,7 CX) comme seuil intéressant. Dans
le jeu Clifford+T standard, CNOT est Clifford (0 T) et Toffoli coûte 7 T ; la mesure de la littérature
XAG est `T = 4 × complexité multiplicative`, valable **quand l'AND est calculé sur un qubit propre**.

| variante | CCX | CX | T | ΔT |
|---|---:|---:|---:|---:|
| baseline | 42 | 433 | 294 | — |
| CX −5 % (411) | 42 | 411 | 294 | **0** |
| CX −10 % (390) | 42 | 390 | 294 | **0** |
| CX −23 % (333) | 42 | 333 | 294 | **0** |
| CCX −1 (41) | 41 | 433 | 287 | **−7** |
| CCX −5 (37) | 37 | 433 | 259 | **−35** |

**Une réduction de CX, même de 23 %, n'achète aucun T.** Elle achète des portes Clifford, donc de la
profondeur et du temps d'exécution sur un matériel à correction d'erreur, mais elle ne déplace pas un
score dominé par T. Une seule CCX en moins vaut 7 T, soit 2,4 %.

Ceci ne rend pas l'objectif CX absurde — la mission demande explicitement de ne pas confondre coût
réversible et coût quantique, et une réduction de CX est un résultat constructif réel. Mais cela
signifie que **le seuil de 5 % de CX, présenté comme particulièrement intéressant, ne peut pas être
présenté comme un gain de score**. Le tableau ci-dessus le chiffre.

Note importante sur le facteur 4 : le gadget 4T/AND de Meuli–Soeken–De Micheli exige un qubit
initialisé à |0⟩. Ce bloc a **zéro scratch** et `z` arrive sale. Le facteur applicable ici est donc
plutôt 7 par Toffoli, et je n'ai **pas** écrit d'émetteur Clifford+T : aucun T-count n'est mesuré pour
un candidat, seulement cette arithmétique de conversion.

---

## 6. Vérification : ce qui est prouvé, et comment

Chaque circuit émis est vérifié deux fois, par deux voies indépendantes.

**Énumération exhaustive (n ≤ 5).** Les `2^(3n)` affectations de `(a, b, z)` sont toutes parcourues :
`a` et `b` restaurés, `z` accumule exactement le produit, aucun fil auxiliaire. 0 échec sur les neuf
circuits.

**Preuve symbolique (toutes largeurs, dont n = 12).** GF(2¹²) a `2³⁶` entrées : l'énumération est
impossible. `proof.py` construit la forme normale algébrique attendue de chaque fil de sortie par
**deux constructions indépendantes** — depuis la table de corps (`gf_mul`), et depuis le jeu de termes
de l'émetteur — vérifie qu'elles coïncident, puis compare fil par fil aux ANF simulées du circuit. Les
ANF étant canoniques, l'égalité fil par fil **est** l'équivalence fonctionnelle sur les `2³⁶` entrées.

`gf_mul` est lui-même recoupé contre l'implémentation indépendante de l'archive du 27 octobre
(`research/archive/2026-10-27/src/field_phase.py`, même modulus `0x1053`) sur les 4096 valeurs de `a`
et 14 valeurs de `b`, et l'irréductibilité de chaque modulus est vérifiée par division exhaustive.

**Mutants rejoués à n = 12** — le vérificateur doit refuser une transformation incorrecte :

| mutant | verdict |
|---|---|
| CCX supprimée | **DIFFERS**, fil 25 |
| contrôles échangés | **DIFFERS**, fil 25 |
| fan-out sur `z` sale | **DIFFERS**, fils 25–35 |
| jeu de termes corrompu | rejeté à l'assertion d'identité tensorielle |

Le mutant « drop-ccx » est celui que la mission nomme (`mutant-drop-ccx.json`), reproduit ici sur mes
propres circuits.

**Aucun certificat n'est transféré** : chaque candidat est prouvé sur son propre hash.

---

## 7. Méthodes essayées et écartées

| piste | issue |
|---|---|
| ordonnancement glouton vs partage de formes | **aucun gain** : multiplicité de forme = 1 partout |
| sélection de base linéaire (300 bases aléatoires) | **aucun gain** : la base naturelle (106) bat toutes les autres (meilleur : 216) |
| réduction du nombre de termes (Karatsuba) | **contre-productif** : 54 termes au lieu de 144, mais 424 CX de repli |
| plancher de rang (incidences minimales) | **contre-productif** : 144 incidences, mais 438 CX de repli |
| réécritures XAG locales (axe B) | **non tentées** : sans la structure réelle, aucune fenêtre à cibler |
| synthèse linéaire PMH (axe C) | **non tentée** : ne s'applique qu'aux transformations de base du bloc réel |

Les trois décompositions mesurées encadrent le problème : elles montrent que dans cette architecture
(3n fils, zéro ancilla, `z` sale, repli/dépli par CX), **il existe un compromis monotone** entre
incidences et repli. Le schoolbook minimise le repli (0) et maximise les CCX (363) ; le plancher de
rang fait l'inverse (144 CCX, 438 CX). La baseline, à 42 CCX / 433 CX, est **meilleure que les trois**
en total (475 contre 363…737 — seule schoolbook a moins de portes, mais avec 363 CCX, donc 2541 T
contre 294). Elle n'est battable que dans la zone étroite autour de son propre compromis, et c'est
précisément la zone que je ne peux pas atteindre sans le générateur réel.

---

## 8. Ce qu'il faudrait pour reprendre

Les quatre fichiers, ou leurs équivalents exportés, et l'accès en lecture :

```
src/qant/blocks/gf12_stateful.py
experiments/blocks/gf12_stateful_20261028/audit/candidate.json
experiments/blocks/gf12_stateful_20261028/audit/witness.json
experiments/blocks/gf12_stateful_20261028/audit/mutant-drop-ccx.json
```

Avec eux, la reprise est courte et ciblée, dans cet ordre :

1. vérifier l'hypothèse `42 = 7 × 6` (Toom-3, 4 blocs de 3) en lisant le générateur ;
2. instrumenter le coût réel : combien des 433 CX sont distribution, combien sont changement de base,
   combien sont restauration — c'est la mesure que la mission demande au §2.3 et que je n'ai pas pu
   faire ;
3. si la restauration domine, appliquer PMH (axe C) à la transformation linéaire effective, en
   comparant au compte actuel ;
4. si la distribution domine, chercher un terme set à 42 termes mais dont les masques `w` sont moins
   denses — c'est la seule variable qui reste, et elle est contrainte par `Σ|w| ≥ 144`.

Le harnais de preuve (`proof.py`) est réutilisable tel quel : il ne dépend d'aucun fichier qant.

---

## 9. Tableau final

`baseline | meilleur candidat | CCX | CX | fils | profondeur | preuve | statut`

| baseline | meilleur candidat | CCX | CX | fils | profondeur | preuve | statut |
|---|---|---:|---:|---:|---|---|---|
| qant GF(2¹²) : 42 CCX / 433 CX | — aucun candidat retenu — | 42 | 433 | 36 | non mesurée | non vérifiable (accès 404) | **BLOCKED** |
| schoolbook (référence) | schoolbook | 363 | 0 | 36 | 321 | ANF exacte, 2³⁶ entrées | référence |
| Karatsuba | Karatsuba | 313 | 424 | 36 | 326 | ANF exacte, 2³⁶ entrées | **STOP** (pire que la baseline) |
| plancher de rang | plancher de rang | 144 | 438 | 36 | 380 | ANF exacte, 2³⁶ entrées | **STOP** (pire que la baseline) |

**Décision : `STOP`.** Aucune amélioration constructive du bloc GF(2¹²) n'a été obtenue ni même
approchée, et les trois décompositions exactes que j'ai pu construire sont toutes pires que la
baseline en coût total. La raison n'est pas un manque d'heuristiques : c'est que les deux leviers
identifiés par la mission (réutilisation de formes, choix de base) sont **morts sur cette fonction** —
multiplicité de forme 1, et base naturelle déjà optimale parmi 300 essayées. Le troisième levier (moins
de termes) est contré par le coût de repli, et le quatrième (moins d'incidences) aussi.

Le seul actif réel de la session est le **plancher d'incidences `Σ|w| ≥ n²`** (section 2), prouvé et
indépendant de qant, plus le harnais de preuve ANF qui rend les futurs candidats GF(2¹²) vérifiables
sans énumération. Les deux sont réutilisables immédiatement dès que le générateur est lisible.

---

## 10. Provenance et reproduction

- Base : `yoch/symq` `main` = `6c4d20a6b0cfb83fe9ecb836ecf8cf5dae9d495c` (« Merge #76 »).
- Branche : `explore/xag-reversible-synthesis-20261028`.
- Python 3.12.3, pytest 9.1.1, ruff 0.17.3. Aucune dépendance nouvelle.

```
research/xag-synthesis/tensor_budget.py    dd319b21c97f970526b1c176ea33449f6b3663019001f111fd6433f86cfa97cb
research/xag-synthesis/decompositions.py   ec09e2b481eb80c18c3854e23dc290bbde2a0af8e62a0a60e702181931ba856d
research/xag-synthesis/proof.py            77f3f34e1490b867dfeabfe09d706c2d117cda5ee3a27749a5374dce25953453
tests/test_xag_decompositions.py           201d82be924cde827a0c3b065bc1aa2730498609225aeb8dc01cb8ab08f26268
```

Reproduction :

```
PYTHONPATH=src /tmp/venv/bin/python research/xag-synthesis/tensor_budget.py
PYTHONPATH=src:/workspace/research/xag-synthesis /tmp/venv/bin/python research/xag-synthesis/decompositions.py
PYTHONPATH=src:/workspace/research/xag-synthesis /tmp/venv/bin/python research/xag-synthesis/proof.py
/tmp/venv/bin/python -m pytest tests/test_xag_decompositions.py -q      # 74 passed, ~90 s
/tmp/venv/bin/ruff check research/xag-synthesis tests/test_xag_decompositions.py
```

Les hashes ci-dessus sont ceux des fichiers après le passage final de `ruff`, c'est-à-dire l'état
exact commité.
