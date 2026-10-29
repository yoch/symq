# Rapport de clôture — qualification SymQ

**29 octobre 2026, vers 16 h 40 (Asia/Jerusalem).** Base mesurée : `yoch/symq` `main` = `2ff32c72ac2e47e01c1cbb9e944f7a8005bd015a`. Aucune pull request n'a été fusionnée par cet audit. Les fusions #90 à #99 sont celles du mainteneur, entre 13 h 22 et 13 h 29 (Asia/Jerusalem) le même jour.

Ce texte sépare deux questions que les chronométrages ont tendance à coller ensemble : l'équivalence **classique** d'une permutation réversible, et l'équivalence d'un **canal quantique HMR**.

## 1. Réponse

**Prouvé, sur un périmètre écrit.**

- L'oracle CPTP de #90, largeur au plus 6, sur toutes les unités `|x⟩⟨y|`.
- La substitution temporelle de #92, pour des permutations classiques totales, transcripts liés.
- L'arithmétique de #93 : bijection colex, certificats duaux GF(2), et ANF fail-closed (9 601 448 paires, 0 résultat faux). Le refus d'un produit dont un monôme intermédiaire dépasse le degré est le contrat de l'issue #86.
- L'annulation de dette de phase de #94, y compris le gadget multi-dettes GF(4)/GF(8), et son égalité de canal avec #90.
- L'identité de factorisation de #95, contre un oracle indépendant (312 unités, 0 écart ; 60/60 verdicts). Le chemin chaud natif est du C.
- Les deux contre-exemples de transitions ci-dessous, rejoués dans cette clôture sur l'oracle dense.

**Prometteur, pas établi hors du laboratoire.**

- Le gain natif de #95 sur les familles synthétiques non linéaires. Ces familles ont `phi0 = 0` et des coefficients `g_j` nuls après réparation : le temps mesure surtout la permutation `F`.
- Le coût plat de #92 quand le circuit grossit. L'exemple favorable est synthétique (cœurs MAC, largeur 70), pas un fragment de compilateur.
- L'utilité de #94 au-delà des gadgets déjà prouvés. Le solveur GF(2) n'est pas un minimiseur de portes.

**Incorrect.** Aucun défaut de soundness dans #90, #92, #93, #94, #95. Le finding « conventions HMR incompatibles » était une erreur d'audit : il est retiré. La référence comparée était `value + reset`, et `reset` décohère.

**Intégration native de production.** Aucune aujourd'hui. #95 est la seule brique dont le C est réel, profilé et sain sous ASan. Elle reste sous `research/` tant qu'un corpus HMR de compilateur, redistribuable, n'a pas été mesuré, et tant que la revendication de vitesse reste bornée au non linéaire.

## 2. Décisions

`MERGE_RESEARCH` veut dire : le code peut vivre dans `main` sous `research/` ou `tests/`, limites écrites, sans contrat d'API stable. La promotion hors de `research/` est une autre décision. Elle est refusée partout.

| Ligne | Décision | Production | État au 29 octobre, 16 h 40 (Asia/Jerusalem) |
|---|---|---|---|
| #90 oracle CPTP | `MERGE_RESEARCH` | non | fusionné par le mainteneur, 13 h 23 |
| #92 substitution temporelle | `MERGE_RESEARCH` | non | fusionné, 13 h 22 |
| #93 ANF colex / GF(2) | `MERGE_RESEARCH` | non | fusionné, 13 h 23 |
| #94 dettes de phase | `MERGE_RESEARCH` | non | fusionné, 13 h 23 ; le `KEEP_EXPERIMENTAL` est levé |
| #95 canal natif C/ZDD | `MERGE_RESEARCH` | non, plus tard si le corpus HMR existe | fusionné, 13 h 22 |
| #96 index public | `MERGE_RESEARCH` | sans objet | fusionné, 13 h 24 |
| #97 audit | `MERGE_RESEARCH` | sans objet | fusionné, 13 h 24 |
| #98 kit GF public | `MERGE_RESEARCH` | sans objet | fusionné, 13 h 24 |
| #101 cartes d'oubli | `MERGE_RESEARCH` | non | **ouverte**, non fusionnée |

Rien n'est `REJECT`. Rien n'est `REQUIRES_FIX` pour la soundness. #99 est un correctif Ruff déjà fusionné (13 h 29), pas une ligne de recherche.

#101 encode les deux contre-exemples physiques et la somme explicite des cartes conditionnées. Son propre texte dit qu'il ne qualifie ni QCEC ni une accélération HMR. Le garder sous `tests/` est le bon statut. Cette clôture ne le fusionne pas.

## 3. Deux théorèmes, deux largeurs

`check_equivalence` construit une algèbre à **une variable par fil**. Le masque natif `uint64_t` admet **64 fils**. `c2_181` (35 fils) et `rd84_313` (34 fils) sont donc éligibles, et ils décident.

`check_full_channel` représente **deux copies cohérentes** du registre de données. La précondition native est `2 * n_data <= 64`, donc `n_data <= 32`. Au-delà, le natif lève `ResourceLimitExceeded`. Le backend Python `zdd` décide encore. Un contrat à 36 bits de données (72 variables appariées) est refusé par le natif et reste décidable en Python. Ce n'est pas la même limite que les 64 fils classiques.

## 4. Transitions de verdict

Les classes ne forment pas une échelle. L'unique arête enregistrée est :

`EQUIVALENT(FULL_QUANTUM_CHANNEL)` implique `EQUIVALENT(TRACED_CHANNEL)`.

`implies` renvoie vrai pour cette arête et pour une classe avec elle-même. Elle renvoie faux pour le sens inverse, pour le passage classique ↔ quantique, et pour le passage canal ↔ instrument.

`restate` et `forget_instrument` n'évaluent aucune matrice. Ils admettent un **changement d'étiquette** sur un résultat que l'appelant a déjà prouvé, et seulement si le verdict est `EQUIVALENT`.

| Transition | `EQUIVALENT` | `DIFFERENT` | `INCONCLUSIVE`, `UNSUPPORTED`, `INTERNAL_ERROR` |
|---|---|---|---|
| `restate` vers `TRACED_CHANNEL` | admis depuis `FULL_QUANTUM_CHANNEL` | refusé | refusé |
| `forget_instrument` vers `FULL_QUANTUM_CHANNEL` | admis depuis `CLASSICAL_OUTPUT_INSTRUMENT` | refusé | refusé |
| `classify_exception` | jamais | jamais | limite de ressource ou temps → `INCONCLUSIVE` ; grammaire → `UNSUPPORTED` ; autre exception → `INTERNAL_ERROR` |

`INTERNAL_ERROR` reste distinct d'`INCONCLUSIVE` : un crash de vérificateur n'est pas un budget épuisé.

### Contre-exemple 1 — X sur une ancille propre

Programmes : l'identité sur 1 fil de donnée et 1 ancille, contre `X` sur cette ancille, ancille initiale `|0⟩`.

- Canal complet (ancille gardée) : `DIFFERENT`.
- Canal après trace partielle sur l'ancille : `EQUIVALENT` (4 unités `|x⟩⟨y|`).

La trace est oublieuse. Un verdict `DIFFERENT` sur l'état complet n'a pas d'image `DIFFERENT` sur l'état tracé. L'égalité tracée est une preuve séparée.

### Contre-exemple 2 — écrasement d'un slot

`measure_z` vers `b0`, contre le même circuit suivi de `store(b0, 0)`.

- Canal CPTP inconditionnel : `EQUIVALENT`.
- Instrument observé sur `b0` : `DIFFERENT`.

Oublier les enregistrements d'un instrument différent ne produit pas un canal différent. La somme des cartes conditionnées est un calcul, pas une conséquence du mot `DIFFERENT`.

## 5. Qualification classique QCEC

Corpus public MIT, dépôt `munich-quantum-toolkit/qcec`, commit `98d6784176bfeb6ef923d4d0220e8d486dc1982f`, manifeste `benchmarks/corpus/qcec/MANIFEST.json`. Circuits réversibles, **sans mesure**. Ils qualifient `FULL_CLASSICAL` seulement.

20 circuits. 19 supportés (largeurs 16–35, portes 22–229). 1 hors grammaire : `c2_182`, rotation `ctrl @ U(...)`, statut manifeste `unsupported`, jamais converti en verdict.

| Split | Circuits | Décidés | Non décidés |
|---|---:|---:|---:|
| dev | 5 | 5 | 0 |
| holdout | 6 | 6 | 0 |
| extension | 9 | 8 | 1 (`c2_182`) |

Protocole de cette clôture, sur `2ff32c7`, neuf répétitions, processus unique, `perf_counter` autour de `check_equivalence`. Chaque circuit supporté est comparé à `mutate` avec un germe dérivé du nom (`1234` mélangé au nom, mélange 32 bits). Sans ce mélange, `Random(1234)` recommencé à chaque fichier tirait `add_control` partout. Avec le mélange, la dernière répétition couvre les cinq édits : `insert` 5, `retarget` 4, `add_control` 4, `drop_control` 4, `delete` 2.

**19/19** différences de sortie, les deux backends, **0 désaccord**. `c2_181` (35) et `rd84_313` (34) décident en natif. Une différence ici est le premier fil de sortie qui diffère. Il n'y a ni noyau de déphasage ni phase dans cette grammaire.

Temps de la médiane par répétition : Python ZDD entre 1,14 ms et 1,31 ms ; natif entre 0,25 ms et 0,31 ms. Médiane des ratios médians appariés (Python/natif), sur les neuf répétitions : **3,92×**. Rapport des médianes de ces médianes de temps : **4,51×**. Les ratios médians des répétitions vont de **3,74× à 4,48×**. Les sorties durant moins d'une milliseconde bougent d'un passage à l'autre ; `cm151a_211` tombe à 1,50× sur la dernière répétition, `apla_203` monte à 9,13×. Le chiffre stable est l'ordre de grandeur, pas une décimale.

Ce facteur est une **détection classique précoce d'un écart de sortie sur un mutant**. Ce n'est pas un résultat HMR, pas un rapport de canaux, pas une preuve que le natif accélère un compilateur quantique.

Les lignes brutes sont dans `research/verification_api/RESULTS/qcec-classical-20261029.json`.

## 6. #95, ce que le chronomètre mesure vraiment

L'identité prouvée est

`E(|x⟩⟨y|) = (-1)^{phi0(x) XOR phi0(y)} [g(x) = g(y)] |F(x)⟩⟨F(y)|`.

Les familles publiées (`research/hmr_native_channel/benchmark.py`) réparent chaque dette. Sur les constructeurs, pour tout assignement de donnée : `phi0 = 0` et chaque `g_j = 0`. Le noyau est tautologique.

- Famille affine (`CX`, HMR, `Z` conditionné, référence vide) : `F` est l'identité. Le résidu est l'overhead d'appel.
- Famille non linéaire (`CCX` partagé, AND temporaire, `CZ` de réparation) : `F` bouge des bits de donnée, identique des deux côtés. Le temps est celui de cette permutation.

Reproduction indépendante déjà archivée (sous-processus neufs, ordre aléatoire), à ne pas confondre avec le chiffre QCEC ci-dessus :

| Famille | data | HMR | Python/natif |
|---|---:|---:|---:|
| affine | 8 | 130 | 0,98× |
| affine | 16 | 500 | 0,98× |
| non linéaire | 8 | 70 | 6,6× |
| non linéaire | 12 | 25 | 2,4× |

Le reçu CI de la PR, SHA `7a75f827`, donne 0,97× / 0,97× / 8,49× / 3,01× sur les mêmes familles. Même conclusion : le natif est neutre sur l'affine, plus rapide quand le produit ZDD non linéaire domine. Trois passages de la reproduction indépendante tenaient 6,6× et 2,4× à ±3 %. Un passage antérieur avait donné 3,5× sur le petit non linéaire : un ratio unique ne se cite pas.

Profil sur `data=8`, `hmr=70` : **1 261** appels C `NativeZDDManager.product` (0,014 s cumulés), contre **215 005** récursions Python `zdd.multiply`. Le chemin natif n'est pas une façade.

`data=32` (64 variables appariées) passe. `data=33` lève `ResourceLimitExceeded`. ASan/UBSan de la campagne d'audit : propre.

## 7. P1 HMR, décision qui tient

Le produit des signes est `(-1)^{m g(x)} * (-1)^{m g(x)} = 1`. En ANF : `m·g XOR m·g = 0`.

Le circuit réparé

`ccx(0,1,3) ; cx(3,2) ; hmr(3, b0) ; cz(0,1 | b0)`

est égal, comme canal, à `ccx(0,1,2)`, ancille gardée et ancille tracée. Les 64 cohérences d'entrée concordent. Le circuit non réparé n'est pas égal à la référence. L'interop publique compte **17/17**. Cette campagne n'a pas été rejouée dans cette clôture : elle est dans l'audit déjà fusionné (`research/audit_crossrepo_20261029/reports/hmr-interop-decision.md`, `tests/test_crossrepo_audit.py`).

La cause de l'erreur retirée : comparer le circuit réparé à `value_ops + reset(ancilla)`. `reset` tue la cohérence. Ce n'est pas le circuit de valeur.

Contrainte qui reste : une correction tardive n'annule la dette que si le monôme enregistré est encore celui de la fonction au moment de la correction. Une porte de valeur qui déplace un fil du monôme entre la mesure et la correction invalide la réparation. #94 recalcule la phase sur les fonctions finales.

## 8. Archive

**`ARCHIVE_NOT_AVAILABLE`.** L'archive privée attendue (65 fichiers, `README_FOR_AGENT.md`, commit source `040baca30fe2bc8f6b8258e8be6a6c76a613e8c4`) n'est pas dans cet environnement. La recherche exhaustive est celle du 29 octobre au matin, consignée dans `research/audit_crossrepo_20261029/reports/archive-status.md`. La clôture a revérifié le workspace, les stores d'agent et les chemins d'upload usuels : toujours rien.

Cette absence laisse non vérifiés les contrats historiques de la référence externe, les preuves HMR/GF(2^12) de cette référence, et le rapport de qualification attaché à `040baca3`. Elle ne bloque pas les conclusions ci-dessus, qui portent sur le code public.

## 9. Ce que cette clôture ajoute

Sous `research/verification_api/` : le contrat typé (`implies`, `restate`, `forget_instrument`, `classify_exception`) et le harnais QCEC. `tests/test_verification_contracts.py` : 21 tests, verts, sur l'arbre `src/` de `2ff32c7` (0,21 s). Les 34 et 35 fils classiques sont exigés décidés par le natif. Les deux contre-exemples physiques refusent le transport de `DIFFERENT`. Les familles #95 réduites (affine 8/4, non linéaire 6/3) ont un noyau et une phase identiquement nuls, et seule la famille non linéaire déplace `F`.

Rien de ceci ne modifie `src/symq/`.
