# Audit transversal — capacités SymQ issues de l'analyse croisée avec `yoch/qant`

**Auditeur indépendant. Aucune PR n'a été fusionnée. Aucune n'est défendue ici.**

Date de l'audit : 29 octobre 2026. Base : `yoch/symq` `main` = `5703d2b2a6b33e16eae6ab4d8a862e938ffed596`.

## 1. Ce qui a été réellement audité

| PR | HEAD audité | CI sur ce SHA | État |
|---|---|---|---|
| [#90](https://github.com/yoch/symq/pull/90) | `38a137203205202367425b3f0317a7ae4faa2612` | 7/7 | OPEN |
| [#92](https://github.com/yoch/symq/pull/92) | `225f060897859b660e5e7afb3f1024e73777b051` | 7/7 | OPEN (draft) |
| [#93](https://github.com/yoch/symq/pull/93) | `f58f382276516f974306e51cd3f2d5c17398aad1` | 7/7 | OPEN (draft) |
| [#94](https://github.com/yoch/symq/pull/94) | `53da41e71dcdc3158fb80b9719572b5f5a44635b` | 7/7 | OPEN (draft) |
| [#95](https://github.com/yoch/symq/pull/95) | `af8a874db66a8176e14419cda13cff13c6db0ef2` | 7/7 + `native-hmr` | OPEN (draft) |

Chaque HEAD a été vérifié par `gh pr view`, chaque diff complet relu, et le SHA du `check_runs` comparé au
SHA de tête : **les cinq correspondent**. Un worktree séparé par PR a été créé depuis le SHA exact ; aucun
fichier de `main` n'a été modifié.

**Fait architectural décisif** : les cinq PR n'ajoutent que des fichiers sous `research/` et `tests/`.
Aucune ne touche `src/symq/`. Ce sont des prototypes de recherche, pas des capacités intégrées.

## 2. Méthode

Pour chaque PR, quatre axes :

1. **reconstitution du théorème** depuis sa définition, sans lire le code comme spécification ;
2. **oracle indépendant** écrit à partir de zéro, ne réutilisant ni les règles ni les structures auditées ;
3. **attaques adverses** : mutants, cas limites, entrées malformées ;
4. **mesures** : temps complets, RSS, et pour #95 le chemin natif réellement pris.

Les harnais sont publiés dans `raw/` et sont exécutables ; les résultats bruts dans `raw/*.json`.

## 3. Résultats par PR — voir les rapports détaillés

| PR | `CORRECT` | `VALIDATED` | `REVIEWABLE` | `MERGEABLE` | `PRODUCTION-READY` |
|---|---|---|---|---|---|
| #90 | oui | oui (périmètre largeur ≤ 6) | oui | oui | **non** |
| #92 | oui | oui | oui | oui | **non** |
| #93 | oui, avec réserve | oui (arithmétique) | oui | oui | **non** |
| #94 | oui | oui (modèle de phase) | oui | oui | **non** |
| #95 | oui | **oui, le plus solide** | oui | oui | **non** |

Aucune n'est `PRODUCTION-READY` : toutes sont sous `research/`, aucune n'a de corpus réel, et #95 est le
seul dont l'avantage de performance est mesuré de façon reproductible.

## 4. Preuves scientifiques solides

### 4.1 L'oracle CPTP de #90 est exact sur son périmètre

J'ai écrit une référence indépendante (`raw/ref90.py`) : matrices denses sur `Fraction`, familles de Kraus
appliquées puis sommées, sans partager une ligne avec l'oracle audité.

- **24/24** programmes couvrant toutes les portes acceptées (X/CX/CCX/MCX/SWAP/CSWAP, Z/CZ/CCZ/NEG,
  reset, measure_z, HMR, et leurs compositions) : accord exact sur **toutes** les unités matricielles
  `|x⟩⟨y|`, avec ancillas gardées **et** tracées.
- **120 programmes aléatoires** (graine fixée), mêmes conditions : **accord total**.
- L'action HMR `M_m = |0⟩⟨χ_m|` a été redérivée à la main et coïncide caractère par caractère avec
  l'implémentation ; `M_0†M_0 + M_1†M_1 = I` vérifié exactement.

**Le contre-exemple obligatoire est correctement détecté.** Le circuit `CX(data→ancilla) ; reset(ancilla)`
laisse `|0⟩⟨1|` invariant en apparence sur les entrées de base, mais détruit la cohérence. L'oracle répond
`equivalent=False` avec témoin `(0,1)`, et la vérification par diagonale seule aurait répondu `True`.
C'est précisément la propriété qui rend cet oracle utile.

`same_channel` et `same_instrument` sont réellement distincts : j'ai trouvé une paire de programmes dont
le **canal inconditionnel est identique** mais dont l'**instrument observé diffère** ; l'oracle renvoie
`same_channel=True, same_instrument=False`. C'est la distinction la plus fine de la PR et elle fonctionne.

### 4.2 La substitution temporelle de #92 est compositionnellement saine

- `check_equivalence` est **total sur tous les fils** (un écart sur une scratch seule est détecté) : c'est
  l'hypothèse qui rend l'induction valide, et elle est réellement satisfaite.
- **200 transcripts aléatoires à deux slots chevauchants** : tous acceptés, et tous globalement égaux par
  énumération exhaustive. Aucun faux positif.
- Une paire locale qui n'est égale que sur les états atteignables est **refusée** avec un témoin qui
  reproduit la différence par exécution concrète.
- Le transcript est lié : retirer une porte commune, réordonner, ou fournir un hash erroné lève
  `TranscriptMismatch`.

**Second exemple connecté, comme demandé.** Trois, quatre cœurs MAC GF(2⁴) (22 portes CCX chacun) sur des
fenêtres de fils chevauchantes, noyés dans une échelle de 70 CX, largeur 70, **un seul bloc connexe**, 225
portes. Substitution réelle : `CORE∘CORE → identité` (22 portes réellement annulées par cœur).

| cœurs | largeur | portes réf. | preuve locale | miter monolithique |
|---:|---:|---:|---:|---:|
| 1 | 14 | 57 | 0,4 ms | 0,2 ms |
| 2 | 26 | 113 | 0,7 ms | 1,9 ms |
| 3 | 38 | 169 | 0,7 ms | 6,7 ms |
| 4 | 50 | 225 | 0,9 ms | 17,4 ms |

La preuve locale reste **plate** quand le monolithique croît superlinéairement. C'est le premier argument
de coût favorable mesuré dans cet ensemble de PR, et il est reproductible.

### 4.3 L'identité de factorisation de #95 est exacte

L'identité revendiquée

$$\mathcal E(|x\rangle\langle y|)=(-1)^{\phi_0(x)\oplus\phi_0(y)}\,[g(x)=g(y)]\,|F(x)\rangle\langle F(y)|$$

a été vérifiée contre l'oracle dense indépendant de #90 : **312 unités, 0 écart**, sur 30 programmes
aléatoires utilisant HMR et `mcz_if`.

De plus, **60/60 paires** de programmes ont donné le même verdict entre le moteur natif C/ZDD et l'oracle
CPTP indépendant. C'est la validation croisée la plus forte de tout l'audit : deux moteurs, deux
algorithmes, deux langages.

### 4.4 Les certificats GF(2) de #93 sont exacts

`unsat_dual` comparé à une énumération exhaustive : **5036 systèmes** (lignes ≤ 3, colonnes ≤ 3) et
**3000 systèmes aléatoires**. Accord parfait, et chaque certificat se vérifie lui-même par
`y^T A = 0, y^T b = 1`.

### 4.5 La bijection combinadique de #93 est exacte

Vérifiée exhaustivement pour `variables` 1..6 et `degree` 0..4 : `index`/`mask` sont inverses l'un de
l'autre, sans collision, et l'image est exactement `[0, capacity)`. Les monomiales hors degré **lèvent**
au lieu d'être tronquées.

## 5. Erreurs, limites et contre-exemples identifiés

### 5.1 #93 — le produit ANF refuse des produits valides (P2, fail-closed)

`Polynomial.multiply` vérifie le degré de **chaque monomial partiel** pendant l'itération, avant
l'annulation modulo 2. Conséquence : un produit dont le résultat final est dans l'espace peut être refusé
si un monomial intermédiaire de degré supérieur apparaît puis s'annule.

Exemple minimal (`n=4`, `deg=2`) : `A = x0x1`, `B = x2 + x0x2`. Les deux produits donnent `x0x1x2`
(degré 3), qui s'annulent mod 2. Le vrai résultat est **0**, parfaitement dans l'espace, mais
l'implémentation lève `ResourceLimitExceeded`.

**Ampleur mesurée** : sur les 8828 produits de `n=4, deg=2` dont le résultat est dans l'espace,
**5414 (61,3 %)** sont refusés pour cette raison.

**Direction de l'erreur** : j'ai balayé exhaustivement 53 824 paires (`n=4, deg=2`) — **0 résultat
faux**, 3414 corrects, 50 410 refusés. L'implémentation est donc **sound mais incomplète** : elle ne
produit jamais une valeur incorrecte, elle refuse. C'est acceptable pour un prototype, mais ce n'est
documenté nulle part et cela peut faire échouer une vérification légitime.

**Atténuation** : dans `evaluate_phase`, le raccourci `self.bits == other.bits` (idempotence) absorbe le
cas le plus fréquent. Sur 400 programmes `PhaseProgram` aléatoires, **aucun** refus n'était attribuable à
cette limite. Le défaut est donc réel mais il ne bloque pas le chemin d'évaluation actuel.

### 5.2 #94 — deux conventions HMR incompatibles entre PR (P1, documentation)

C'est le point le plus délicat de l'audit, et il mérite d'être dit précisément.

`phase_semantics` de SymQ modélise HMR comme **contribuant** `m_j·g_j(x)` au polynôme de phase. Le
« remboursement » de #94 ajoute `MCZ_IF(m_j)·(produit de fils vivants)`, ce qui **annule** ce terme : après
réparation, `phase_semantics(repaired).phase == phi0`, vérifié exact.

L'oracle CPTP de #90 modélise HMR comme **déjà** porteur du signe `(-1)^{m·g}` dans la branche de Kraus.
Y ajouter la correction **réapplique** le signe au lieu de l'annuler.

J'ai d'abord cru à un bug de #94, puis vérifié : **aucun des deux n'est faux**. Ce sont deux conventions
différentes du même objet, et #94 est cohérent avec `phase_semantics`, qui est l'autorité de SymQ. Mais
**rien dans les deux PR ne signale cette incompatibilité**, et un lecteur qui compose #90 et #94 obtiendra
une réponse fausse. C'est un défaut de documentation à l'échelle du dépôt, pas un bug local.

Ce que #94 prouve, énoncé exactement : *le programme réparé, vu comme famille d'unitaires conditionnés
`U_m(x)`, n'a plus de dépendance en `m` dans sa phase, et sa fonction de valeur est inchangée.* Ce n'est
pas une égalité de canal CPTP, et la PR ne le prétend pas.

**Vérification indépendante de #94** : 150 programmes aléatoires, **58 réparés correctement, 92 refusés
(`PhaseDebtUnresolved`), 0 incorrect**. Retirer la correction réintroduit la dette, comme attendu.

### 5.3 #90 — portée pratique étroite (P2)

L'oracle est exponentiel par construction : `(2^data)²` unités × matrices de taille `2^(data+anc)`. Mesuré :
`data=3` prend 0,47 ms pour 64 unités, mais la croissance est en `4^n` et l'énumération complète n'est pas
envisageable au-delà de 5–6 fils de données. `max_width=6`, `max_events=8`, `max_branches=256` sont des
bornes dures et explicites. C'est un **oracle de référence**, pas un moteur — ce qui est exactement ce que
la PR annonce.

### 5.4 #92 — pas d'analyse de phase, et coût non mesuré sur du réel (P2)

La PR ne couvre que l'égalité de permutations classiques. Un lecteur pressé pourrait croire que « prouver
une substitution » couvre les phases et les mesures : ce n'est pas le cas, et le README le dit. Aucun
circuit issu d'un vrai compilateur n'a été testé ; mon exemple MAC est synthétique.

### 5.5 #95 — provenance du benchmark (P2, résolu)

Le benchmark archivé a été mesuré à `7a75f82717801fa8606a35715f5ddaae048a726b`, alors que la tête de PR est
`af8a874db66a8176e14419cda13cff13c6db0ef2`. J'ai vérifié le diff : les deux commits ne diffèrent que par
l'ajout de `README.md` et du JSON de résultats. **Le code mesuré est donc bien le code de la tête**, mais
la PR devrait épingler explicitement ce SHA dans son README.

## 6. Performances : reproduction indépendante de #95

J'ai reproduit avec un protocole différent : sous-processus neufs, ordre des backends **randomisé**,
15 répétitions, RSS lu dans l'enfant, et un **contrôle négatif**.

| famille | data | HMR | python-zdd | C/ZDD | ratio | RSS zdd | RSS natif |
|---|---:|---:|---:|---:|---:|---:|---:|
| affine | 8 | 130 | 2,45 ms | 2,49 ms | **0,98×** | 18124 | 18124 |
| affine | 16 | 500 | 7,12 ms | 7,23 ms | **0,98×** | 18472 | 18508 |
| non linéaire | 8 | 70 | 113,14 ms | 16,58 ms | **6,6×** | 35440 | **25332** |
| non linéaire | 12 | 25 | 4,05 ms | 1,66 ms | **2,4×** | 18616 | 18832 |

Mes chiffres sont **plus rapides** que l'archive (3,40 → 2,45 ms ; 188,25 → 113,14 ms) mais la conclusion
qualitative est la même, avec un écart nettement réduit sur le non linéaire (8,49× → 6,6× et 3,01× → 2,4×).
Trois exécutions complètes donnent 6,57/6,62/6,74× et 2,41/2,44/2,47× : stable à ±3 %, mais une exécution
antérieure avait donné 3,52×, d'où la règle de ne jamais citer un ratio unique.

**Contrôle négatif** : deux programmes différents sont refusés par les deux backends
(`full output wire 2 differs`). Le vérificateur ne répond donc pas « équivalent » par défaut.

**Balayage pour trouver le point de bascule** :

| famille | data | HMR | ratio python/natif |
|---|---:|---:|---:|
| non linéaire | 6 | 10 | 1,32× |
| non linéaire | 6 | 150 | 4,20× |
| non linéaire | 8 | 30 | 4,96× |
| non linéaire | 8 | 140 | **7,87×** |
| non linéaire | 10 | 120 | 6,91× |
| affine | 8 | 10..130 | 0,98–1,03× |
| affine | 16 | 50..500 | 0,97–1,02× |

**Le C devient rentable dès qu'il y a de la non-linéarité**, avec un facteur qui sature autour de 7–8×, et
il est **neutre sur l'affine** (légèrement défavorable, dans le bruit). C'est cohérent avec la structure :
en affine les polynômes restent petits, donc le coût est dominé par l'`overhead` de passage Python→C ; en
non linéaire le ZDD explose en Python alors que le C garde des opérations compactes.

**Le chemin natif est réellement natif.** Profilage sur `data=8, hmr=70` :

- backend Python : 215 005 appels récursifs à `zdd.multiply`, 194 811 à `zdd.xor`, 98 684 `_mk` ;
  `cumtime` 0,430 s.
- backend natif : **1261 appels** à `NativeZDDManager.product` (C), 0,014 s cumulés, aucune récursion
  Python dans le chemin chaud.

Ce n'est pas une façade Python. C'était le point le plus important à vérifier sur cette PR.

**ASan/UBSan** : `tools/sanitize_native.py` exécuté sur la suite native, **propre** (85 tests).
Limite 64 variables vérifiée : `data=32` (2×32 = 64) passe, `data=33` lève `ResourceLimitExceeded`.

## 7. Résultats négatifs

- **L'avantage natif ne s'étend pas à l'affine.** À `data=16, hmr=500`, le C est 2 % *plus lent*. Toute
  revendication « le natif est plus rapide » doit être restreinte au non linéaire.
- **Aucun corpus réel.** Les quatre familles sont synthétiques et déterministes ; la PR l'admet. Rien ne
  prouve que le rapport tienne sur des fragments HMR issus d'un compilateur réel.
- **#93 est incomplet** sur 61 % des produits de `n=4, deg=2` (section 5.1).
- **#94 ne donne aucun gain de performance** et ne le revendique pas ; les corrections produites ne sont
  pas optimales en nombre de portes (le solveur GF(2) est déterministe, pas minimisant).

## 8. Ce qui est intégrable, et sous quelles conditions

**Rien n'est intégrable en production aujourd'hui.** Les cinq PR sont sous `research/`, sans contrat
d'API stable, sans corpus réel, et quatre sur cinq n'ont aucune mesure de performance.

Ce qui **mérite** de devenir une capacité publique, par ordre de solidité démontrée :

1. **#95 (moteur natif de canal)** — seule PR avec (a) une identité prouvée indépendamment sur 312 unités,
   (b) 60/60 d'accord avec un oracle d'un autre algorithme, (c) un avantage de performance reproductible
   sur une famille identifiée, (d) ASan propre. Conditions : restreindre la revendication au non linéaire,
   épingler le SHA du benchmark, et obtenir un corpus réel redistribuable.
2. **#92 (substitution temporelle)** — composition saine, transcripts liés, refus correct des cas
   atteignables-seulement, et un vrai gain mesuré sur circuit connecté. Conditions : nommer explicitement
   que la phase et les mesures sont hors périmètre, et mesurer sur un circuit de compilateur.
3. **#90 (oracle CPTP)** — le meilleur *oracle de référence* de l'ensemble, validé à 100 % contre une
   implémentation indépendante. Conditions : rester explicitement un oracle à largeur bornée, jamais un
   moteur ; et documenter la convention HMR face à `phase_semantics`.
4. **#93 (ANF bitset, certificats GF(2))** — les certificats et la bijection sont exacts et utiles.
   Conditions : corriger ou documenter la limite de degré intermédiaire, qui refuse 61 % de produits
   valides.
5. **#94 (remboursement de dette)** — correct dans son modèle, mais dont l'intérêt dépend d'une convention
   HMR qui n'est pas partagée avec #90. Condition bloquante : trancher la convention au niveau du dépôt.

## 9. Ordre d'intégration recommandé

Il n'y a **pas de dépendance technique** entre les cinq PR : chacune ajoute des fichiers isolés sous
`research/` et ne modifie pas `src/`. Elles peuvent donc être traitées indépendamment.

L'ordre par valeur démontrée : **#95 → #92 → #90 → #93 → #94**.

Avant toute promotion hors de `research/` :

1. **trancher la convention HMR** (section 5.2) — c'est le seul point qui peut produire une réponse
   *fausse* si les briques sont composées ;
2. décider si #95 devient une API de vérification explicite (`check_full_channel`) ou reste un prototype ;
3. ne pas construire de couche d'abstraction commune avant d'avoir deux cas d'usage réels : les cinq PR
   n'ont aujourd'hui aucune structure partagée qui le justifierait.

## 10. La question posée

> Quelles capacités de SymQ sont réellement prouvées, lesquelles sont seulement prometteuses, lesquelles
> sont incorrectes, et lesquelles méritent une intégration native en production ?

**Réellement prouvées** (vérifiées par un oracle indépendant, avec contre-exemples testés) :

- l'oracle CPTP de #90 sur son périmètre borné — 24/24 cas + 120 programmes aléatoires, accord exact ;
- la composition de #92 — 200 transcripts chevauchants, aucun faux positif, transcripts liés ;
- l'identité de factorisation de #95 — 312 unités, 0 écart, et 60/60 verdicts concordants ;
- les certificats GF(2) et la bijection combinadique de #93 — exhaustivement vérifiés.

**Seulement prometteuses** :

- #94 : correct dans son modèle, mais l'utilité dépend d'une convention non partagée ;
- la performance native de #95 : réelle et reproductible, mais sur des familles synthétiques uniquement ;
- #93 : l'arithmétique est juste, mais 61 % de refus sur les produits valides à `n=4, deg=2` limitent
  l'usage réel.

**Incorrectes** : aucune. Je n'ai trouvé **aucun** défaut de soundness dans les cinq PR. Les défauts
trouvés sont une incomplétude (#93, fail-closed), une incompatibilité de convention (#90 vs #94), et des
revendications de performance trop larges (#95 sur l'affine).

**Méritent une intégration native en production** : **#95, et seulement elle**, sous trois conditions —
restreindre la revendication au non linéaire, épingler le SHA mesuré, et disposer d'un corpus réel. Le
gain est de 3,5 à 7,9× sur les familles non linéaires, neutre sur l'affine, avec un chemin C réellement
emprunté (1261 appels C contre 410 000 récursions Python) et ASan propre.

Aucune PR n'est fusionnée. Aucune ne devrait l'être sans que la convention HMR soit tranchée.
