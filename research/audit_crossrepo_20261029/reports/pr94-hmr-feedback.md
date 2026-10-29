# PR #94 — Synthèse de corrections de dettes de phase HMR (issue #91)

**SHA audité : `53da41e71dcdc3158fb80b9719572b5f5a44635b`** · CI 7/7 · OPEN (draft)

## Qualification

| | |
|---|---|
| **CORRECT** | oui, dans son modèle de phase |
| **VALIDATED** | oui — 150 programmes, 0 incorrect |
| **REVIEWABLE** | oui |
| **MERGEABLE** | oui, **après** que la convention HMR soit tranchée (voir §5) |
| **PRODUCTION-READY** | **non** — aucune mesure de coût, corrections non optimales |

## Théorème revendiqué

Étant donné un `PhaseProgram` dont la phase est affine en événements de mesure :

$$\phi(x,m)=\phi_0(x)\oplus\bigoplus_j m_j\,g_j(x),$$

construire des corrections `Z`/`CZ`/`CCZ` **en fin de programme**, contrôlées classiquement par un
événement immuable, de sorte que la phase résiduelle du programme réparé soit **exactement** `φ₀`, les
fonctions de sortie inchangées et toutes les ancillas propres.

L'identité utilisée : si `v_t(x)` sont les valeurs encore vivantes sur les fils à la fin, on cherche
`g_j = ⊕_t c_{j,t} · ∏_{q∈t} v_q`, puis on émet un `MCZ_IF(m_j)` par terme sélectionné. Le système est
résolu sur GF(2) par élimination déterministe (voir `_elimination`).

## Audit mathématique

J'ai vérifié la décomposition `_coefficients` sur l'exemple documenté
`p = mcx(0,1,3); cx(3,2); hmr(3)` :

```
phase ANF          : {0b1011}  =  m0 · (x0 ∧ x1)
base (sans m)      : {}
dette par événement: [ {0b11} ]  =  x0 ∧ x1        <- correct
```

La correction choisie est `CZ(0,1)`, dont la monomiale est bien `x0 ∧ x1`. Le solveur a donc sélectionné
la réponse juste.

Après réparation : `phase_semantics(repaired).phase == {}` et `outputs` identiques. La dette est annulée.

**Non-affinité** : un terme avec deux bits d'outcome (`outcome_bits.bit_count() > 1`) lève
`PhaseDebtUnresolved("nonaffine measurement-outcome term")`. C'est le bon comportement — une extension
future de l'IR ne doit pas hériter silencieusement du théorème.

## Vérification indépendante

**150 programmes aléatoires** (largeurs 1–3, 1–2 ancillas, réseau de valeur + HMR) :

| issue | nombre |
|---|---:|
| réparés, obligations vérifiées | **58** |
| refusés (`PhaseDebtUnresolved`) | 92 |
| **incorrects** | **0** |

Les refus sont attendus : quand les produits de fils vivants ne couvrent pas la dette (typiquement une
dette qui n'est plus exprimable sur les fils restants), la PR refuse plutôt que d'inventer.

**Mutant** : retirer la correction réintroduit la dette (le `phase` redevient `m0·(x0∧x1)`). Un test qui
accepterait le programme non corrigé serait donc pris en défaut.

## Findings

| gravité | finding |
|---|---|
| **P1** | **Incompatibilité de convention HMR avec #90.** `phase_semantics` fait *contribuer* `m_j g_j` à la phase ; l'oracle CPTP de #90 modélise HMR comme *déjà* porteur du signe dans la branche de Kraus. Les deux sont cohérents en interne, mais composer les briques donne un résultat faux. Rien ne le signale. Voir le rapport transversal §5.2. |
| **P2** | Les corrections ne sont **pas** optimales en nombre de portes : `_elimination` est déterministe et glouton sur les pivots, pas un minimiseur. La PR le dit. |
| **P2** | `_native_check` est un audit des équations booléennes, pas du canal. Le README le dit, mais le nom `audit_backend="zdd-native"` peut suggérer une preuve quantique native. |
| **P2** | Aucune mesure de coût (temps, RSS) ; la PR ne revendique aucun avantage de performance. |
| **P2** | Le « gadget non trivial distinct du AND temporaire » demandé par la mission n'est pas démontré sur un cas réaliste ; l'exemple reste `x0∧x1` sur une ancilla temporaire. |

Aucun finding P0.

## Ce que la PR prouve exactement

Il faut être précis, car c'est là que la lecture rapide induit en erreur.

La PR prouve : *le programme réparé, vu comme famille d'unitaires conditionnés `U_m(x)`, n'a plus de
dépendance en `m` dans sa phase, et sa fonction de valeur est inchangée.*

Elle ne prouve **pas** : une égalité de canal CPTP, ni que le programme réparé est physiquement le même
circuit que l'original. Le remboursement **déplace** la phase d'une contribution de mesure vers une porte
explicite conditionnée. C'est un objectif légitime (rendre la dette explicite et vérifiable), et c'est ce
que le code fait.

J'ai initialement cru à un double comptage parce que je comparais au canal CPTP de #90 ; l'analyse
détaillée montre que les deux PR ne parlent pas du même objet. Voir le rapport transversal.

## Décision

**`MERGEABLE`** comme prototype de recherche, **à condition** que la convention HMR soit tranchée au niveau
du dépôt avant toute composition avec #90. **`VALIDATED`** dans son modèle.
**Pas `PRODUCTION-READY`** : pas de mesure de coût, corrections non optimales, pas de gadget réaliste.
