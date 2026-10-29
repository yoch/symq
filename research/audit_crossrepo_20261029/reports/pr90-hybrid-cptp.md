# PR #90 — Oracle CPTP hybride (issue #85)

**SHA audité : `38a137203205202367425b3f0317a7ae4faa2612`** · CI 7/7 sur ce SHA exact · OPEN

## Qualification

| | |
|---|---|
| **CORRECT** | oui, dans le périmètre inspecté |
| **VALIDATED** | oui — 24/24 cas + 120 programmes aléatoires contre un oracle indépendant |
| **REVIEWABLE** | oui — README, théorème et bornes explicites |
| **MERGEABLE** | oui (aucun bloqueur technique) |
| **PRODUCTION-READY** | **non** — oracle exponentiel borné à 6 fils, sous `research/` |

## Théorème revendiqué

Un canal CPTP exact pour une grammaire hybride fermée : portes réversibles, phases diagonales, HMR en base
X, mesure Z, reset véritable, et portes de valeur ou de signe contrôlées par un résultat mesuré.

L'identité centrale, pour `M` événements :

$$\mathcal E(\rho)=\sum_{m\in\{0,1\}^M}K_m\rho K_m^{\dagger},\qquad K_m=|0\rangle\langle\chi_m|\ \text{(par qubit mesuré)}$$

## Hypothèses

- entrée : **tout** état cohérent sur les fils de données ; **toutes** les ancillas dans `|0⟩` ;
- comparaison sur **toutes** les unités matricielles `|x⟩⟨y|`, pas seulement les diagonales ;
- événements HMR **immuables** et distincts des slots classiques mutables ;
- largeur bornée (`max_width=6`), événements bornés (`max_events=8`), branches bornées (`max_branches=256`) ;
- aucune mesure/reset gardée par un bit classique (rejeté à la validation).

## Audit mathématique — vérifié indépendamment

J'ai réécrit l'action HMR depuis la définition « mesurer en base X puis reset » et comparé :

```
M_0 = 1/2 [[1,1],[1,1]]        M_1 = 1/2 [[1,-1],[-1,1]]
M_0†M_0 + M_1†M_1 = I          (conservation de trace, exacte)
```

La formule de l'implémentation `Fraction(-1 if m and (a^b) else 1, 2)` coïncide **caractère par
caractère** avec cette dérivation sur les quatre entrées `(a,b)`.

**Référence indépendante** (`../raw/ref90.py`) : matrices denses sur `Fraction`, familles de Kraus
appliquées puis sommées, écrites depuis la liste des portes, sans partager de code.

- **24/24** programmes (identité, X, CX, CCX, MCX-4, SWAP, CSWAP, Z, CZ, CCZ, NEG, reset, measure_z, HMR,
  et compositions dont `cx+reset`, `cx+hmr`, `hmr` deux fois, `ccx+reset`) : **accord exact** sur toutes
  les unités, ancillas gardées **et** tracées.
- **120 programmes aléatoires** (graine `20261029`), même protocole : **accord total**.

Note méthodologique : ma première version de la référence était **fausse** — j'avais fusionné les deux
opérateurs de reset en un seul `|0⟩⟨0| + |0⟩⟨1|`. La version correcte garde `{|0⟩⟨0|, |0⟩⟨1|}` séparés.
C'est ma référence qui était en défaut, pas l'implémentation ; le désaccord m'a fait vérifier à la main.

## Le contre-exemple obligatoire

Programme : `CX(data→ancilla) ; reset(ancilla)`, ancilla initialement `|0⟩`.

| test | verdict |
|---|---|
| sur les seules entrées de base (diagonales) | **identique à l'identité** — le piège |
| sur toutes les unités (implémentation) | **`equivalent=False`**, témoin `(0,1)` |

Sur `|0⟩⟨1|`, la cohérence de données est **détruite** (`{}` au lieu de `{(0,1): 1}`). Un vérificateur qui
ne regarderait que les valeurs classiques certifierait ce circuit à tort. **Cet oracle ne tombe pas dans
le piège**, et c'est la propriété qui justifie son existence.

## `same_channel` vs `same_instrument`

J'ai construit une paire dont le **canal inconditionnel est identique** mais dont l'**instrument observé
diffère** :

```python
p1 = measure_z(0, "b0")
x(0, condition="b0")
p2 = measure_z(0, "b0")
x(0, condition="b0")
store("b0", 0)
```

| requête | résultat |
|---|---|
| `same_channel(p1,p2)` | **True** |
| `same_instrument(p1,p2, observed_slots=("b0",))` | **False** |

La distinction est réelle, implémentée, et correcte. C'est la partie la plus fine de la PR.

## Tests adversariaux — tous refusés pour la bonne raison

| entrée | comportement |
|---|---|
| condition sur un slot non initialisé | `UnsupportedOperation: uninitialized classical condition` |
| mesure sans slot | `UnsupportedOperation: measurement needs a classical slot` |
| mesure gardée | `UnsupportedOperation: measurement/reset cannot be guarded` |
| fil hors largeur / fil répété | rejeté |
| arité incorrecte | `TypeError` |
| porte inconnue | `UnsupportedOperation: unsupported 'h'` |
| `data=True` (bool) | rejeté |
| `oxor` depuis un slot non initialisé | rejeté |
| largeur 3 pour un programme de 4 fils | `ResourceLimitExceeded: width` |

Réutilisation du **même slot** par deux mesures : acceptée (c'est légitime), et l'identité d'événement
reste distincte.

## Performances et ressources

Oracle exponentiel assumé : `(2^data)²` unités × matrices `2^(data+anc)`.

| data | unités | temps |
|---:|---:|---:|
| 1 | 4 | 0,10 ms |
| 2 | 16 | 0,14 ms |
| 3 | 64 | 0,47 ms |

Événements HMR : 1 → 0,03 ms ; 6 → 0,38 ms ; 9 → `ResourceLimitExceeded` (borne `max_events=8`).

**Ce n'est pas un moteur de production et la PR ne le prétend pas.** C'est un oracle de référence pour
valider des vérificateurs scalables — exactement l'usage auquel je le recommande.

## Findings

| gravité | finding |
|---|---|
| **P2** | La convention HMR diffère de celle de `symq.phase` utilisée par #94 (voir rapport transversal §5.2). Aucune mention dans le README. Un lecteur qui compose les deux obtient une réponse fausse. |
| **P2** | La docstring de `same_channel` dit « linearity makes the full set of matrix units a complete basis » — exact, mais mérite d'être relié explicitement au fait que cela exclut les canaux non linéaires en l'état des entrées. |

Aucun finding P0 ou P1.

## Décision

**`MERGEABLE`** comme prototype de recherche sous `research/`. **`VALIDATED`** sur son périmètre.
**Pas `PRODUCTION-READY`** : oracle exponentiel, borne 6 fils, pas de corpus réel.

La valeur réelle est d'être l'**oracle de référence** contre lequel un moteur scalable (#95) peut être
validé — et c'est exactement ce que j'ai fait : 60/60 verdicts concordants entre #95 et cet oracle.
