# Rapport de qualification SymQ

**Dernière mise à jour : 29 octobre 2026, 17 h 05 (Asia/Jerusalem).** Base : `yoch/symq` `main` =
`2ff32c72ac2e47e01c1cbb9e944f7a8005bd015a`. Aucune pull request n'a été fusionnée par cet audit.

Ce texte sépare deux questions que les chronométrages ont tendance à coller ensemble : l'équivalence
**classique** d'une permutation réversible, et l'équivalence d'un **canal quantique HMR**.

## 0. Correctif du 29 octobre — un contrat de preuve qui ne mentait pas, mais qui ne savait pas

La première version de `contracts.py` conservait `(verdict, classe de théorème)` et rien d'autre.
La revue de #102 a montré que ce couple est ambigu : `EQUIVALENT(CLASSICAL_OUTPUT_INSTRUMENT)`
décrit **deux** énoncés physiques différents selon que les ancillas ont été tracées ou conservées.

Le contre-exemple, rejoué ici sur l'oracle dense indépendant, avec 1 bit de donnée et 1 ancille propre :

```python
L = HybridProgram(1, 1).store("b0", 0)
R = HybridProgram(1, 1).x(1).store("b0", 0)
```

| propriété | résultat mesuré |
|---|---|
| instruments après trace de l'ancilla | **égaux** |
| instruments avec ancilla conservée | **différents** |
| canaux quantiques après trace | **égaux** |
| canaux quantiques complets | **différents** |

L'ancien `forget_instrument()` renvoyait `EQUIVALENT(FULL_QUANTUM_CHANNEL)` dans les deux cas. Sur la
ligne « instruments tracés », c'était donc un théorème **faux** : la preuve ne portait que sur le canal
réduit. Défaut de soundness dans l'adaptateur de recherche de #102, pas dans l'oracle hybride audité.

### Le correctif : un cadre physique dans le certificat

`ProofResult` porte désormais un `PhysicalFrame` immuable qui nomme :

- les programmes comparés et leur empreinte SHA-256 (validée comme un digest hexadécimal de 64 caractères) ;
- le domaine d'entrée et sa sémantique cohérente (`Domain.points`, `Domain.coherent_span`) ;
- l'hypothèse de préparation des ancillas (`AncillaContract.clean`) ;
- les sorties quantiques **conservées**, les sorties **tracées**, et parmi les conservées, celles
  qui sont des **ancillas** (`ancilla_outputs`) ;
- les slots classiques observés ;
- la classe de théorème effectivement démontrée ;
- le verdict, le témoin éventuel et le nombre de paires vérifiées.

Une conversion ne peut que **rétrécir** ce cadre :

| opération | entrée | sortie | ce qu'elle ne fait pas |
|---|---|---|---|
| `restate(…, TRACED_CHANNEL)` | `EQUIVALENT(FULL_QUANTUM_CHANNEL)` | `EQUIVALENT(TRACED_CHANNEL)`, ancillas déplacées vers `traced_outputs` | ne calcule aucune trace partielle |
| `forget_instrument` | `EQUIVALENT(CLASSICAL_OUTPUT_INSTRUMENT)` | `FULL_QUANTUM_CHANNEL` si les ancillas étaient conservées, **`TRACED_CHANNEL`** sinon | ne somme aucune carte conditionnée |

Les deux refusent tout verdict autre que `EQUIVALENT`, et refusent d'inventer une ancille à tracer
(`with_ancillas_traced()` échoue si `ancilla_outputs` est vide). `certifies()` / `require_certificate()`
comparent les huit champs du cadre : changer un programme, son empreinte, le domaine, le contrat
d'ancillas, une sortie ou un slot invalide le certificat.

**Architecture retenue : A** (transformation de certificat), pas B. Le module ne fait volontairement
aucune algèbre linéaire : les textes de `restate` et `forget_instrument` disent explicitement que la
trace et la somme ne sont pas recalculées ici. Un appelant qui veut la somme vérifiée exécute l'oracle
(`research.hybrid_channel.oracle`) ou le kit indépendant de #101. C'est la plus petite construction
honnête : elle ne peut pas surinterpréter, parce qu'elle ne peut pas prétendre avoir calculé.

**Ce qui reste refusé, et pourquoi** :

- `DIFFERENT(FULL_QUANTUM_CHANNEL)` → pas de `DIFFERENT(TRACED_CHANNEL)` : `X` sur une ancille propre
  est visible avant la trace et invisible après.
- `DIFFERENT(CLASSICAL_OUTPUT_INSTRUMENT)` → pas de canal différent : `measure_z` puis `store` du même
  slot change l'enregistrement et laisse la carte CPTP intacte.
- `INCONCLUSIVE`, `UNSUPPORTED`, `INTERNAL_ERROR` ne traversent aucune conversion.
- `INTERNAL_ERROR` reste distinct d'`INCONCLUSIVE` : un crash n'est pas un budget épuisé.

### Gardes éprouvées par mutants

Douze mutants ont été injectés dans des copies du module, chacun devant faire échouer la suite :

| mutant injecté | détecté |
|---|---|
| `forget_instrument` renvoie toujours `FULL_QUANTUM_CHANNEL` | oui |
| `restate` accepte `DIFFERENT` | oui |
| `forget_instrument` accepte `DIFFERENT` | oui |
| un crash devient `INCONCLUSIVE` | oui |
| le cadre ignore le désaccord contrat/partition de trace | oui |
| un canal complet garde des slots observés | oui |
| `certifies` ignore les empreintes | oui |
| `certifies` ignore le domaine | oui |
| la trace déplace aussi les sorties de données | oui |
| backend natif absent → `unsupported_input` | oui |
| erreur interne → `unsupported_input` | oui |
| backend indisponible compté comme accord | oui |
| `require_native` retombe silencieusement en Python | oui |
| plafond de largeur native supprimé | oui |
| totaux par split mélangent indisponible et décidé | oui |

### Mode pure-Python

La CI du commit `d793c8b` était **6/7** : le job `pure-python` échouait (2 échecs, 2826 réussis, 210
ignorés). Cause : sans l'extension C, `check_equivalence(..., backend="zdd-native")` lève, et le
harnais capturait **toute** exception en `outcome="unsupported"`. Les 19 circuits supportés devenaient
artificiellement non supportés, `agreement` trouvait 0 comparaison, et deux assertions tombaient.

Les catégories sont maintenant séparées :

| catégorie | signification |
|---|---|
| `equivalent` / `output_difference` | décision réelle |
| `backend_unavailable` | le moteur demandé n'est pas installé — propriété de la **machine**, pas du circuit |
| `inconclusive` | budget ou limite de nœuds atteints |
| `internal_error` | exception inattendue, diagnostic conservé |
| `unsupported_input` | le manifeste déclare le fichier hors grammaire (`c2_182` uniquement) |

`backend_problem()` décide avant tout chargement ; `requested_backends(require_native=True)` lève si le
C manque alors qu'il était attendu. Résultats mesurés :

| mode | circuits `zdd` décidés | comparaisons natives | total |
|---|---:|---:|---|
| avec C natif | **19/19** | 19, 0 désaccord | `pytest -q` : **3825 passed, 2 skipped** |
| pure-Python (extension bloquée à l'import) | **19/19** | 0 (aucune ligne fictive) | **3044 passed, 14 skipped** |

Le test pure-Python n'est pas un drapeau monkeypatché : il bloque `symq.backends.zdd_native` par un
`MetaPathFinder` dans un sous-processus, donc il emprunte exactement le chemin que la CI a pris.

## 1. Réponse

**Prouvé, sur un périmètre écrit.**

- L'oracle CPTP de #90, largeur au plus 6, sur toutes les unités `|x⟩⟨y|`.
- La substitution temporelle de #92, pour des permutations classiques totales, transcripts liés.
- L'arithmétique de #93 : bijection colex, certificats duaux GF(2), ANF fail-closed (9 601 448 paires,
  0 résultat faux). Le refus d'un produit dont un monôme intermédiaire dépasse le degré est le contrat
  de l'issue #86.
- L'annulation de dette de phase de #94, gadget multi-dettes GF(4)/GF(8) compris, et son égalité de
  canal avec #90.
- L'identité de factorisation de #95 contre un oracle indépendant (312 unités, 0 écart ; 60/60 verdicts).
  Le chemin chaud natif est du C.
- Les transitions de certificat ci-dessus, avec leurs deux contre-exemples physiques.

**Prometteur, pas établi hors du laboratoire.**

- Le gain natif de #95 sur les familles synthétiques non linéaires. Ces familles ont `phi0 = 0` et des
  `g_j` nuls après réparation : le temps mesure surtout la permutation `F`.
- Le coût plat de #92 quand le circuit grossit. L'exemple favorable est synthétique (cœurs MAC,
  largeur 70), pas un fragment de compilateur.
- L'utilité de #94 au-delà des gadgets déjà prouvés. Le solveur GF(2) n'est pas un minimiseur de portes.

**Incorrect.** Aucun défaut de soundness dans #90, #92, #93, #94, #95. Le finding « conventions HMR
incompatibles » était une erreur d'audit, retirée : la référence comparée était `value + reset`, et
`reset` décohère. Le défaut corrigé ici était dans l'**adaptateur** de #102, pas dans ces cinq lignes.

**Intégration native de production.** Aucune. #95 reste la seule brique dont le C est réel, profilé et
sain sous ASan, et elle reste sous `research/`.

## 2. Décisions

`MERGE_RESEARCH` veut dire : le code peut vivre dans `main` sous `research/` ou `tests/`, limites
écrites, sans contrat d'API stable ni promesse de maintenance. La promotion hors de `research/` est une
autre décision, refusée partout.

| Ligne | Décision | Production | État au 29 octobre, 17 h 05 (Asia/Jerusalem) |
|---|---|---|---|
| #90 oracle CPTP | `MERGE_RESEARCH` | non | fusionné par le mainteneur, 13 h 23 |
| #92 substitution temporelle | `MERGE_RESEARCH` | non | fusionné, 13 h 22 |
| #93 ANF colex / GF(2) | `MERGE_RESEARCH` | non | fusionné, 13 h 23 |
| #94 dettes de phase | `MERGE_RESEARCH` | non | fusionné, 13 h 23 ; `KEEP_EXPERIMENTAL` levé |
| #95 canal natif C/ZDD | `MERGE_RESEARCH` | non, plus tard si le corpus HMR existe | fusionné, 13 h 22 |
| #96 index public | `MERGE_RESEARCH` | sans objet | fusionné, 13 h 24 |
| #97 audit | `MERGE_RESEARCH` | sans objet | fusionné, 13 h 24 |
| #98 kit GF public | `MERGE_RESEARCH` | sans objet | fusionné, 13 h 24 |
| #101 cartes d'oubli | `MERGE_RESEARCH` | non | ouverte |
| #102 contrat + qualification | **`MERGE_RESEARCH`** après ce correctif | non | corrigée dans cette passe |

Rien n'est `REJECT`. #99 est le correctif Ruff déjà fusionné (13 h 29).

### Traitement proposé pour #101

#101 apporte les cinq fixtures physiques toutes-cohérences, indépendantes de mon adaptateur. Après ce
correctif, trois de ses propriétés sont couvertes par `tests/test_verification_contracts.py` (les deux
contre-exemples et la réparation HMR). Il reste chez #101 deux apports que je ne duplique pas :

1. la somme **explicite** des cartes conditionnées, recalculée matrice par matrice (`_forget_classical`) ;
2. la trace partielle recalculée indépendamment (`_trace_ancillas`).

Proposition : garder #101 ouverte comme **oracle de référence indépendant**, et y ajouter une note
pointant vers #102 pour dire que l'adaptateur ne fait plus de conversion non justifiée. Ne pas fusionner
avant que le mainteneur tranche : la valeur de #101 est justement de rester une seconde implémentation
écrite sans lire la mienne.

## 3. Deux théorèmes, deux largeurs

`check_equivalence` construit une algèbre à **une variable par fil**. Le masque natif `uint64_t` admet
**64 fils** ; `c2_181` (35) et `rd84_313` (34) décident donc en natif.

`check_full_channel` représente **deux copies cohérentes** du registre de données. La précondition native
est `2 * n_data <= 64`, donc `n_data <= 32`. Au-delà, le natif lève `ResourceLimitExceeded` ; le backend
Python `zdd` décide encore. Un contrat à 36 bits de données (72 variables appariées) est refusé par le
natif et reste décidable en Python. Ce n'est pas la même limite.

## 4. Qualification classique QCEC — deux campagnes distinctes

Corpus public MIT, dépôt `munich-quantum-toolkit/qcec`, commit
`98d6784176bfeb6ef923d4d0220e8d486dc1982f`, manifeste `benchmarks/corpus/qcec/MANIFEST.json`. Circuits
réversibles, **sans mesure**. Ils qualifient `FULL_CLASSICAL` seulement.

20 circuits. 19 supportés (largeurs 16–35, portes 22–229). 1 hors grammaire : `c2_182`, rotation
`ctrl @ U(...)`, statut manifeste `unsupported`, jamais converti en verdict.

| Split | Circuits | Décidés | Non décidés |
|---|---:|---:|---:|
| dev | 5 | 5 | 0 |
| holdout | 6 | 6 | 0 |
| extension | 9 | 8 | 1 (`c2_182`) |

### Campagne 1 — historique, conservée telle quelle

`RESULTS/qcec-classical-20261029.json`, 9 répétitions en processus unique, germe `1234` mélangé au nom
du circuit, mutants seulement. Médiane des ratios médians appariés **3,92×**, rapport des médianes de
temps **4,51×**, fourchette des médianes de répétition 3,74×–4,48×. **Ce fichier n'est pas réécrit.**

### Campagne 2 — isolée, appareillée, avec équivalents réels

`RESULTS/qcec-campaign-20261029.json`, produite par `research/verification_api/campaign.py` :

- **un sous-processus neuf** par (circuit, backend, répétition, type de paire) ;
- ordre des backends **mélangé** par germe dérivé de (circuit, répétition, type) ;
- germe de campagne `20261029`, **différent** de celui de la campagne 1 ;
- 7 répétitions, deux types de paires : `mutant` (doit différer) et `equivalent_variant`
  (réécritures sémantiquement préservantes, doivent être **équivalentes**) ;
- temps séparés : chargement, mutation, vérification, rejeu du témoin ; CPU, wall et RSS par ligne ;
- témoin concret conservé et **rejoué** par exécution (`left.run(witness) != right.run(witness)`).

532 lignes. **266 accords, 0 désaccord, 0 paire indisponible.** Tous les mutants sont
`output_difference`, tous les équivalents sont `equivalent`, tous les témoins rejouent.

| type de paire | backend | médiane de vérification |
|---|---|---:|
| mutant | Python `zdd` | 1,119 ms |
| mutant | `zdd-native` | 0,288 ms |
| équivalent | Python `zdd` | 0,997 ms |
| équivalent | `zdd-native` | 0,182 ms |

Ratios appariés par répétition : médiane **4,04×** sur les mutants (min 0,54×, max 6,14×) et **5,75×**
sur les équivalents (min 1,93×, max 10,06×).

**Résultat négatif conservé** : le minimum de 0,54× sur les mutants signifie que le natif a été environ
deux fois **plus lent** sur au moins un circuit et une répétition. Un rapport positif médian ne vaut pas
pour chaque cas, et une sortie sous la milliseconde reste dominée par le bruit de l'hôte.

### Ce que ces chiffres ne sont pas

Ce sont des gains d'**équivalence réversible classique**. Aucun résultat HMR, aucun rapport de canal,
aucune preuve que le natif accélère un compilateur quantique ne peut en être déduit. Les circuits n'ont
ni mesure ni phase, et `check_equivalence` ne construit jamais de noyau de déphasage.

**Holdout** : les 6 circuits holdout ont déjà été inspectés pendant cette qualification. Ils ne sont plus
aveugles pour de futures heuristiques. Toute nouvelle heuristique entraînée sur eux exige un **nouveau**
holdout distinct ; le manifeste actuel ne le fournit pas.

## 5. #95, ce que le chronomètre mesure

L'identité prouvée est

`E(|x⟩⟨y|) = (-1)^{phi0(x) XOR phi0(y)} [g(x) = g(y)] |F(x)⟩⟨F(y)|`.

Les familles publiées réparent chaque dette. Sur les constructeurs, pour tout assignement de donnée :
`phi0 = 0` et chaque `g_j = 0`. Le noyau est tautologique. L'affine laisse `F` identique à l'entrée ; le
non linéaire déplace `F`, identique des deux côtés. Un test de cette suite vérifie ces deux faits sur les
constructeurs réduits (affine 8 données / 4 HMR, non linéaire 6 / 3).

Reproduction indépendante déjà archivée (sous-processus neufs, ordre aléatoire) :

| Famille | data | HMR | Python/natif |
|---|---:|---:|---:|
| affine | 8 | 130 | 0,98× |
| affine | 16 | 500 | 0,98× |
| non linéaire | 8 | 70 | 6,6× |
| non linéaire | 12 | 25 | 2,4× |

Le reçu CI au SHA `7a75f827` donne 0,97× / 0,97× / 8,49× / 3,01×. Profil du cas 8/70 : **1 261** appels
C `NativeZDDManager.product` contre **215 005** récursions Python. `data = 32` passe, `data = 33` lève
`ResourceLimitExceeded`. ASan/UBSan propre.

## 6. P1 HMR

`(-1)^{m g(x)} · (-1)^{m g(x)} = 1`, soit `m·g XOR m·g = 0` en ANF.

Le circuit réparé `ccx(0,1,3) ; cx(3,2) ; hmr(3, b0) ; cz(0,1 | b0)` est égal, comme canal, à
`ccx(0,1,2)`, ancille gardée et ancille tracée, sur les 64 cohérences d'entrée. Le circuit non réparé ne
l'est pas. L'interop publique compte 17/17 (campagne antérieure, non rejouée ici).

Cette suite ajoute trois mutants de réparation, tous détectés : correction **absente**, correction
**doublée** (le signe ne s'applique qu'une fois), correction **décalée** (le `CZ` porte sur d'autres fils
que le monôme enregistré). Aucun n'est confondu avec l'égalité.

## 7. Archive

**`ARCHIVE_NOT_AVAILABLE`**, inchangé. L'archive privée attendue (commit source
`040baca30fe2bc8f6b8258e8be6a6c76a613e8c4`) est absente ; recherche exhaustive consignée dans
`research/audit_crossrepo_20261029/reports/archive-status.md`. Les contrats historiques de cette
référence et son rapport de qualification restent non vérifiés. Aucune conclusion ci-dessus n'en dépend.

## 8. Reproductibilité

```bash
python -m pytest -q tests/test_verification_contracts.py
python -m ruff check .
python -m research.verification_api.campaign --repetitions 7 \
    --out research/verification_api/RESULTS/qcec-campaign-20261029.json
```

Rien de ceci ne modifie `src/symq/`. Aucune dépendance à un dépôt privé.
