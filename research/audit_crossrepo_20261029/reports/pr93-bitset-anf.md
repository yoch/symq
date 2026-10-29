# PR #93 — ANF combinadique, bitsets sur domaine fini, certificats GF(2) (issue #86)

**SHA audité : `f58f382276516f974306e51cd3f2d5c17398aad1`** · CI 7/7 · OPEN (draft)

## Qualification

| | |
|---|---|
| **CORRECT** | oui — aucun résultat faux trouvé |
| **VALIDATED** | oui pour l'arithmétique et les certificats ; **partiel** pour l'expressivité |
| **REVIEWABLE** | oui |
| **MERGEABLE** | oui, avec la limite de degré documentée |
| **PRODUCTION-READY** | **non** — incomplet sur 61 % des produits à `n=4, deg=2` |

## Les trois sous-ensembles, examinés séparément

### 1. ANF combinadique — exact

**Bijection rang colex / monôme.** Vérifiée **exhaustivement** pour `variables` 1..6 et `degree` 0..4 :

- `mask(index(m)) == m` et `index(mask(i)) == i` sur tout le domaine ;
- aucune collision : l'image de `index` est exactement `[0, capacity)` ;
- `capacity == Σ_{d≤deg} C(variables, d)`, recalculé indépendamment.

**Annulation modulo 2.** `from_masks` fait `bits ^= 1 << index(mask)`, donc deux monômes identiques
s'annulent. Vérifié sur 65 accords exacts avec une référence ensembliste indépendante.

**Idempotence `x² = x`.** Vérifiée : `p·p == p` pour trois polynômes dont un de degré plein.

**Pas de troncature.** Une monomiale hors degré **lève** `ResourceLimitExceeded`, elle n'est jamais
silencieusement abandonnée. C'est la bonne direction d'erreur.

#### Finding P2 — refus de produits valides (fail-closed)

`multiply` vérifie le degré de **chaque monomial partiel** pendant l'itération, avant l'annulation mod 2.
Un produit dont le résultat final est dans l'espace peut donc être refusé.

**Reproducer minimal** (`n=4`, `deg=2`) :

```python
A = x0x1            # masques {0b0011}
B = x2 + x0x2       # masques {0b0100, 0b0101}
A*B : x0x1x2 + x0x1x2 = 0   (degré 3 s'annule, résultat final = 0, dans l'espace)
implémentation -> ResourceLimitExceeded: degree limit exceeded: observed 3, limit 2
```

**Ampleur** : sur les 8828 produits de `n=4, deg=2` dont le résultat est dans l'espace, **5414 (61,3 %)**
sont refusés pour cette raison. Ce taux dépend fortement de `n` et `deg` : sur le domaine exhaustif
`n ≤ 5`, `deg ≤ 3` (9 601 448 paires), **973 316 refus sont évitables, soit 10,1 %**, avec des pointes
locales à 32 % (`n=4, deg=3`) et des planchers à 0 % (`deg=n`).

**Direction de l'erreur**, balayage exhaustif de 53 824 paires :

| catégorie | nombre |
|---|---:|
| résultat correct | 3414 |
| refusé (à tort) | 50 410 |
| **résultat faux** | **0** |

L'implémentation est donc **sound mais incomplète** : elle ne renvoie jamais une valeur incorrecte. Pour
un prototype de recherche dont le but est de ne pas mentir, c'est le bon compromis — mais ce n'est
documenté nulle part, et une vérification légitime peut échouer sans explication.

**Atténuation mesurée** : dans `evaluate_phase`, le raccourci `self.bits == other.bits` (idempotence)
absorbe les cas où les deux facteurs sont identiques. Sur **400 programmes `PhaseProgram` aléatoires**,
**aucun** refus n'était attribuable à cette limite. Le défaut est réel mais ne bloque pas le chemin
d'évaluation actuel.

**Recommandation** : soit itérer sur les monômes dans un espace temporaire de degré `2·deg` puis réduire à
la fin, soit documenter explicitement « refuse tout produit dont un monomial intermédiaire dépasse le
degré ». La seconde option est moins risquée pour un prototype.

### 2. Domaine légal fini — correct

- domaine explicite, non vide, **haché** (`sha256` sur `{data, ancillas_zero, points}`) ;
- points dupliqués rejetés ; points hors largeur rejetés ;
- les ancillas sont déclarées initialisées à zéro dans le hash du contrat ;
- `PackedPhase.violations()` refuse O1 (ancilla sale) et O2 (phase dépendant des résultats) ;
- instructions non couvertes : `ValueError("unsupported instruction")`.

**Ce que ce n'est pas** : une comparaison de tables de vérité sur le domaine légal n'est **pas** une
équivalence CPTP, et la docstring le dit. Je n'ai trouvé aucun endroit où la PR promeut l'une en l'autre.

### 3. Certificats GF(2) — exacts

`unsat_dual` produit un témoin dual `y` tel que `yᵀA = 0` et `yᵀb = 1`, puis `verify_dual` le revérifie.

Comparaison à une énumération exhaustive indépendante :

| test | nombre | résultat |
|---|---:|---|
| systèmes exhaustifs (lignes ≤ 3, colonnes ≤ 3) | 5036 | **accord parfait** |
| systèmes aléatoires (graine 7) | 3000 | **accord parfait**, certificats auto-vérifiants |

Aucun cas où un système satisfiable reçoit un certificat, ni l'inverse.

## Findings

| gravité | finding |
|---|---|
| **P2** | `multiply` refuse les produits valides dont un monomial intermédiaire dépasse le degré : 61,3 % à `n=4, deg=2`, **10,1 % sur le domaine exhaustif `n ≤ 5`** (973 316 refus évitables sur 9 601 448 paires). Sound, mais incomplet et non documenté. |
| **P2** | Le benchmark (`benchmark.py`) compare les ANF compactes à `sparse`/`packed`/`zdd`/`zdd-native` ; je n'ai pas reproduit ces chiffres, faute de budget dans cette mission, et je ne les reprends donc pas à mon compte. |
| **P2** | L'extension C n'est justifiée par aucun goulot mesuré dans cette PR ; la PR ne le recommande pas non plus, ce qui est correct. |

Aucun finding P0 ou P1.

## Performances

Non reproduites dans cet audit, et volontairement non revendiquées ici. La PR ne présente pas de gain de
performance comme argument de promotion, seulement un pilote de taille.

## Décision

**`MERGEABLE`** comme prototype de recherche, à condition de documenter la limite de degré intermédiaire.
**`VALIDATED`** pour la bijection combinadique, l'annulation mod 2, l'idempotence et les certificats GF(2).
**Pas `PRODUCTION-READY`** : incomplétude sur une majorité de produits, et aucun gain mesuré indépendamment.

Les certificats GF(2) et la bijection sont les deux éléments réellement réutilisables.
