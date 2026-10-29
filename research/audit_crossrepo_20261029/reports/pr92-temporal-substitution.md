# PR #92 — Substitutions temporelles sur circuits connectés (issue #89)

**SHA audité : `225f060897859b660e5e7afb3f1024e73777b051`** · CI 7/7 · OPEN (draft)

## Qualification

| | |
|---|---|
| **CORRECT** | oui |
| **VALIDATED** | oui — 200 transcripts chevauchants, aucun faux positif |
| **REVIEWABLE** | oui — le README nomme explicitement la frontière de confiance |
| **MERGEABLE** | oui |
| **PRODUCTION-READY** | **non** — pas de circuit de compilateur, périmètre purement classique |

## Théorème revendiqué

Soit deux flux réversibles complets `A` et `B` de largeur `w`, découpés en une séquence ordonnée
d'opérations **communes** (identiques des deux côtés) et de **slots** de substitution locale. Si pour
chaque slot le remplacement local est une **permutation totale égale** sur tous ses fils locaux, alors les
deux flux globaux sont égaux sur **toutes** les entrées et **toutes** les sorties.

L'argument est une induction sur la séquence : le cadre extérieur est l'identité, et chaque slot préserve
l'état global sur ses fils.

## Hypothèses — et pourquoi elles sont réellement satisfaites

La solidité de l'induction repose entièrement sur le fait que la preuve locale soit **totale**, et non
« égale sur les états atteignables ». Je l'ai vérifié directement :

```
check_equivalence(a, b) où a et b ne diffèrent QUE sur une scratch
-> equivalent=False, output=2, witness=0
```

L'égalité locale couvre donc bien tous les fils, scratchs et accumulateurs inclus, avec des entrées
arbitraires. C'est l'hypothèse critique et elle tient.

Autres hypothèses, toutes vérifiées :

- les maps locaux→globaux sont **injectifs** (`non-injective local-to-global map` sinon) ;
- les deux flux reconstruits doivent correspondre **exactement** aux tuples de portes fournis ;
- les hashes SHA-256 des deux sources sont fournis par l'appelant et comparés au contenu réel ;
- le cache de lemmes est **local au processus** et sa clé contient les deux programmes immuables, le
  contrat `preserved`, le backend et le budget.

## Tests adversariaux

| attaque | résultat |
|---|---|
| retirer une porte commune du transcript | `TranscriptMismatch` |
| permuter deux étapes | `TranscriptMismatch` |
| fournir un hash source erroné | `TranscriptMismatch` |
| map local non injectif | `ValueError` |
| map pointant hors largeur | `ValueError` |
| paire locale égale seulement sur les états atteignables | **refusée**, témoin rejoué et différent par exécution |
| les deux côtés restent identiquement sales, `preserved` déclaré | **refusée** (`does not restore its preserved wires`) |
| même paire sale sans `preserved` | acceptée (correct : rien n'est promis) |
| `max_expanded_gates` trop petit | `ResourceLimitExceeded` |
| budget de temps expiré | `ResourceLimitExceeded` |

**200 transcripts aléatoires à deux slots chevauchants** (largeurs 3–5, paires d'identités composées) :
tous acceptés, et **tous** vérifiés globalement égaux par énumération exhaustive. Aucun faux positif.

## Second exemple connecté (demandé par l'audit)

Trois puis quatre cœurs MAC GF(2⁴) — 22 portes CCX chacun, `z ^= a·b` modulo `x⁴+x+1` — placés sur des
fenêtres de fils **chevauchantes**, noyés dans une échelle de CX reliant tous les fils.

Substitution **réelle** : `CORE∘CORE → identité`, soit 22 portes réellement annulées par cœur.

| cœurs | largeur | blocs connexes | portes réf. | preuve locale | miter monolithique |
|---:|---:|---:|---:|---:|---:|
| 1 | 14 | 1 | 57 | 0,4 ms | 0,2 ms |
| 2 | 26 | 1 | 113 | 0,7 ms | 1,9 ms |
| 3 | 38 | 1 | 169 | 0,7 ms | 6,7 ms |
| 4 | 50 | 1 | 225 | **0,9 ms** | **17,4 ms** |

Largeur 70 avec trois cœurs : 137 portes, un seul bloc connexe, prouvé en 1,0 ms ; le miter monolithique
n'est même pas praticable à cette largeur avec `zdd-native` (limite 64 variables).

**La preuve locale reste plate quand le monolithique croît superlinéairement.** C'est le premier argument
de coût favorable mesuré dans cet ensemble de PR, et il est reproductible. Il ne prouve pas une supériorité
générale : sur un seul cœur, la composition est plus lente (0,4 vs 0,2 ms) à cause du surcoût fixe.

## Ce que la PR ne prouve pas — et qu'elle dit

- **aucune phase, aucune mesure, aucun HMR** : c'est de l'égalité de permutations classiques ;
- **aucune correction de l'algorithme de référence** : si les deux flux sont identiques, elle prouve qu'ils
  sont identiques, pas que l'un est « juste » ;
- le rapport JSON n'est **pas** un certificat vérifiable (pas de LRAT, pas de Lean) : la frontière de
  confiance inclut le moteur symbolique de SymQ et Python. Le README le dit explicitement, ce qui est rare
  et mérite d'être souligné.

## Findings

| gravité | finding |
|---|---|
| **P2** | Le titre et la présentation peuvent laisser croire que « prouver une substitution » couvre phases et mesures. Le README est clair, mais un nom comme `verify_classical_transcript` réduirait l'ambiguïté. |
| **P2** | Aucun circuit issu d'un vrai compilateur. Mon exemple MAC est synthétique ; il faudrait un fragment produit par un flot de compilation réel. |
| **P2** | Le hash est calculé par l'appelant, qui peut le calculer depuis l'entrée non fiable elle-même. Le README le dit ; une API qui prend un `Circuit` et un hash **séparément obtenus** serait plus sûre. |

Aucun finding P0 ou P1.

## Décision

**`MERGEABLE`** comme prototype de recherche. **`VALIDATED`** pour l'égalité de permutations classiques.
**Pas `PRODUCTION-READY`** : périmètre étroit, aucune donnée de compilateur réel.

C'est, avec #95, la PR dont le gain de coût est réellement démontré.
