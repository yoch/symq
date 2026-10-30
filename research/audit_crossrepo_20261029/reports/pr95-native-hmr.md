# PR #95 — Moteur HMR natif C/ZDD avec factorisation des issues (issue #50)

**SHA audité : `af8a874db66a8176e14419cda13cff13c6db0ef2`** · CI 7/7 + `native-hmr` · OPEN (draft)

C'est la PR la plus importante de l'ensemble, et celle dont j'ai testé le plus de propriétés.

## Qualification

| | |
|---|---|
| **CORRECT** | oui |
| **VALIDATED** | **oui — la plus solide des cinq** |
| **REVIEWABLE** | oui |
| **MERGEABLE** | oui |
| **PRODUCTION-READY** | **non** — familles synthétiques uniquement, pas de corpus réel |

## Théorème revendiqué

Pour la grammaire sign/HMR restreinte, la factorisation

$$\phi(x,m)=\phi_0(x)\oplus\bigoplus_j m_j\,g_j(x)$$

permet d'éviter l'énumération des `2^M` issues. Le canal complet (toutes les ancillas conservées) vaut

$$\mathcal E(|x\rangle\langle y|)=(-1)^{\phi_0(x)\oplus\phi_0(y)}\,[g(x)=g(y)]\,|F(x)\rangle\langle F(y)|.$$

## Vérification indépendante de l'identité

Contre l'oracle CPTP dense de #90 — un algorithme entièrement différent (matrices de densité exactes,
familles de Kraus explicites) :

**312 unités matricielles, 30 programmes aléatoires avec HMR et `mcz_if` : 0 écart.**

Chaque unité `|x⟩⟨y|` a été comparée entrée par entrée, y compris le noyau `[g(x)=g(y)]` (les unités hors
noyau doivent donner la matrice nulle) et le signe `(-1)^{φ₀(x)⊕φ₀(y)}`.

C'est la validation la plus forte de tout l'audit : deux moteurs, deux algorithmes, deux langages, zéro
divergence.

## Vérification indépendante des verdicts

J'ai construit 60 paires de programmes aléatoires dans la grammaire commune, et comparé le verdict du
moteur natif à celui de l'oracle CPTP indépendant :

**60/60 verdicts concordants, 0 divergence.**

## Le chemin natif est réellement natif

C'était le point le plus important à vérifier : une « accélération native » qui passerait en réalité par
Python serait un faux positif majeur. Profilage sur `data=8, hmr=70` :

| backend | appels dans le chemin chaud | cumtime |
|---|---|---:|
| `zdd` (Python) | 215 005 `zdd.multiply` + 194 811 `zdd.xor` + 98 684 `_mk` (tous récursifs Python) | 0,430 s |
| `zdd-native` | **1261** appels `NativeZDDManager.product` (C) | 0,014 s |

Aucune récursion Python dans le chemin chaud du backend natif. `make_algebra("zdd-native", …)` renvoie
bien `symq.backends.zdd_native.NativeZDDAlgebra` avec un manager C. **Ce n'est pas une façade.**

## Reproduction des performances

Protocole **différent** de celui de la PR, pour éviter de reproduire ses biais : sous-processus neufs à
chaque mesure, ordre des backends **randomisé**, 15 répétitions, RSS lu dans l'enfant, contrôle négatif.

| famille | data | HMR | python-zdd | C/ZDD | ratio | RSS zdd | RSS natif |
|---|---:|---:|---:|---:|---:|---:|---:|
| affine | 8 | 130 | 2,45 ms | 2,49 ms | **0,98×** | 18124 | 18124 |
| affine | 16 | 500 | 7,12 ms | 7,23 ms | **0,98×** | 18472 | 18508 |
| non linéaire | 8 | 70 | 113,14 ms | 16,58 ms | **6,6×** (6,57–6,82) | 35440 | **25332** |
| non linéaire | 12 | 25 | 4,05 ms | 1,66 ms | **2,4×** (2,41–2,47) | 18616 | 18832 |

Comparaison avec l'archive de la PR (`7a75f82`) :

| famille | archive python | mon python | archive natif | mon natif | archive ratio | mon ratio (stable) |
|---|---:|---:|---:|---:|---:|---:|
| affine 8/130 | 3,40 ms | 2,45 ms | 3,50 ms | 2,49 ms | 0,97× | **0,98×** |
| affine 16/500 | 12,89 ms | 7,12 ms | 13,34 ms | 7,23 ms | 0,97× | **0,98×** |
| non linéaire 8/70 | 188,25 ms | 113,14 ms | 22,17 ms | 16,58 ms | 8,49× | **6,6×** |
| non linéaire 12/25 | 5,69 ms | 4,05 ms | 1,89 ms | 1,66 ms | 3,01× | **2,4×** |

**La conclusion qualitative est confirmée, les magnitudes ne le sont pas.** Mes temps absolus sont plus
rapides sur trois cas sur quatre (machine différente), l'écart sur le non linéaire 8/70 est **réduit** de
8,49× à 6,6×, et celui sur le non linéaire 12/25 l'est encore plus fortement, de 3,01× à **2,4×**.

**Variance mesurée** : trois exécutions indépendantes complètes donnent 6,57 / 6,62 / 6,74× et
2,41 / 2,44 / 2,47×. Les ratios sont stables à ±3 % ; en revanche une exécution antérieure sur machine
encore chargée avait donné 3,52× pour le 12/25, ce qui montre que le premier passage après un build
(chaud/froid) peut fausser une mesure isolée. Personne ne devrait citer un ratio unique sans protocole.

## Point de bascule

Balayage pour localiser où le C devient rentable :

| famille | data | HMR | ratio python/natif |
|---|---:|---:|---:|
| non linéaire | 6 | 10 | 1,32× |
| non linéaire | 6 | 80 | 3,90× |
| non linéaire | 6 | 150 | 4,20× |
| non linéaire | 8 | 30 | 4,96× |
| non linéaire | 8 | 70 | 6,6× |
| non linéaire | 8 | 140 | **7,87×** |
| non linéaire | 10 | 60 | 7,80× |
| non linéaire | 10 | 120 | 6,91× |
| affine | 8 | 10–130 | 0,98–1,03× |
| affine | 16 | 50–500 | 0,97–1,02× |

**Le C est rentable dès qu'il y a de la non-linéarité**, sature autour de 7–8×, et reste **neutre** sur
l'affine. L'explication est structurelle : en affine les polynômes restent petits, le coût est dominé par
le passage Python→C ; en non linéaire le ZDD explose en Python alors que le C conserve des opérations
compactes.

## Contrôle négatif

Deux programmes **différents** sont refusés par les deux backends :
`equivalent=False, reason="full output wire 2 differs"`. Le vérificateur ne répond donc pas « équivalent »
par défaut, et le RSS natif plus faible sur le non linéaire (25332 vs 35440 KiB) n'est pas un artefact
d'un chemin qui saute le travail.

## Limites, bornes et robustesse

| test | résultat |
|---|---|
| `data=32` (2×32 = 64 variables) | accepté |
| `data=33` (2×33 = 66 variables) | `ResourceLimitExceeded: native pair variables` |
| occurrence HMR non fraîche (outcome dupliqué) | `UnsupportedOperation` |
| `mcz_if` avant tout `hmr` | `ValueError: feed-forward may only use an earlier measurement outcome` |
| porte hors grammaire (`reset`) | `UnsupportedOperation: 'reset' is outside the fragment` |
| porte inconnue (`h`) | `UnsupportedOperation: 'h' is outside the fragment` |
| budget `max_events` / `max_ops` | `ResourceLimitExceeded` |
| programme muté pendant la vérification | `RuntimeError` (re-hash avant retour) |

Précision sur la dernière ligne : les portes hors grammaire sont refusées par `PhaseProgram.validate()` et
par le vérificateur de canal, mais **pas à la construction** — un `PhaseProgram` peut être instancié avec
un `Op("h", …)` et n'échouer qu'au `validate()`. Ce n'est pas un défaut de soundness (aucun chemin
n'accepte la porte), mais l'échec est plus tardif que ne le suggère « rejette les opérations inconnues ».

**ASan/UBSan** : `tools/sanitize_native.py` exécuté sur la suite native — **propre**, 85 tests.

**Témoins** : chaque témoin natif est rejoué par un interpréteur entier indépendant (`_scalar`) qui ne
construit aucune ANF et ne consulte pas le moteur C. Un témoin qui ne se reproduit pas lève
`RuntimeError`. C'est le bon design : le moteur ne certifie pas ses propres témoins.

## Findings

| gravité | finding |
|---|---|
| **P2** | Le benchmark archivé est mesuré à `7a75f82717801fa8606a35715f5ddaae048a726b`, alors que la tête est `af8a874`. J'ai vérifié le diff : seuls `README.md` et le JSON de résultats ont été ajoutés, donc le code mesuré **est** le code de tête. Mais la PR devrait épingler ce SHA explicitement dans son README plutôt que de le laisser dans le JSON. |
| **P2** | Les quatre familles sont synthétiques et déterministes. La PR l'admet dans `limitations`. Aucune donnée issue d'un compilateur réel. |
| **P2** | Les ratios de l'archive (8,49× et 3,01×) ne se reproduisent pas exactement (6,6× et 2,4× chez moi). Toute citation doit être datée et attribuée à une machine. |
| **P2** | Le RSS est le pic du processus entier (interpréteur inclus), pas le tas natif seul. La PR le dit ; une mesure `maxrss` différentielle serait plus informative. |

Aucun finding P0 ou P1. **Je n'ai trouvé aucun défaut de soundness.**

## Décision

**`MERGEABLE`** et **`VALIDATED`** — c'est la PR la mieux étayée de l'ensemble.

**`PRODUCTION-READY` : non**, pour trois raisons précises et non négociables en l'état :

1. les mesures portent sur des familles synthétiques, pas sur des fragments HMR réels ;
2. la revendication « natif plus rapide » doit être **restreinte au non linéaire** — sur l'affine, le C est
   neutre à légèrement plus lent, et c'est un résultat négatif à conserver ;
3. le SHA mesuré doit être épinglé dans le README.

Sous ces conditions, #95 est la **seule** PR de l'ensemble qui mérite une intégration native en production.
