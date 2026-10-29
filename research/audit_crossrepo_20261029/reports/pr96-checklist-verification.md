# Complément d'audit — vérification des huit points de la PR #96

**Ressource auditée : `research/external_audit/2026-10-29/README.md` @ `7a6f71a35bfd86413620baa9f904644606c950e7`**

Rapport principal : [`../README.md`](../README.md). Ce document ne remplace rien : il **ajoute** la
vérification des points que la checklist #96 énumère et que le premier passage n'avait pas tous couverts.

---

## 1. La ressource elle-même

PR #96 ajoute **un seul fichier de 32 lignes**, aucune ligne de code, sous
`research/external_audit/2026-10-29/`. Elle ne modifie pas `src/`.

### Liens vérifiés

| lien dans le document | état |
|---|---|
| les cinq PR #90..#95 | résolvent (`gh pr view` sur chacune) |
| `.../blob/research/native-hmr-channel-20261029/research/hmr_native_channel/RESULTS/paired-native-20261029.json` | **résout** — blob `2f9f8ee…`, 7668 octets, conforme à `git rev-parse` sur ce même chemin dans `af8a874` |
| `actions/runs/40839531614` | **résout** — workflow « Native HMR research benchmark », `conclusion=success`, `headSha=7a75f827…` |
| `AGENTS.md` sur `main` | **résout** — blob `fa6481e…` |

### Affirmations de provenance — toutes exactes

Le document affirme trois choses que j'ai vérifiées indépendamment :

1. le SHA mesuré est `7a75f82717801fa8606a35715f5ddaae048a726b` → **exact**, confirmé par le JSON *et*
   par le run CI ;
2. « le C/ZDD a perdu légèrement sur deux microcas affine et gagné sur deux cas non linéaires » →
   **exact** (0,97× et 0,97× contre 8,49× et 3,01× dans l'archive ; 0,98× / 0,98× / 6,6× / 2,4× dans ma
   reproduction) ;
3. « ce n'est pas suffisant pour une revendication de ROI en production » → **je souscris**, et c'est la
   conclusion de mon propre rapport.

Le document ne revendique aucun test externe comme exécuté. C'est la bonne posture.

---

## 2. Les huit points obligatoires — résultats

| # | point | statut | preuve |
|---|---|---|---|
| 1 | comparer **toutes** les cohérences `\|x⟩⟨y\|`, pas les seules sorties de base | **vérifié** | le piège canonique `CX;reset` : diagonales identiques (`True`), toutes les unités différentes (`False`) |
| 2 | distinguer canal (enregistrements oubliés) et instrument (sorties classiques observées) | **vérifié** | paire trouvée avec canal identique et instrument différent |
| 3 | distinguer HMR, reset CPTP arbitraire, et reset d'un qubit prouvé propre | **vérifié** | trois cas séparés ci-dessous |
| 4 | muter feedback HMR, signes de phase, identités d'événement, slots, ancillas empruntées | **vérifié** | 10 mutations, toutes attrapées |
| 5 | muter préfixe, suffixe, embedding local, fils préservés, flux sources épinglés | **vérifié** | 7 mutations, toutes attrapées |
| 6 | refuser le débordement de degré ANF ; épuiser `n≤5` ; vérifier les certificats duaux GF(2) | **vérifié** | 9 601 448 paires, **0 résultat faux** ; 5036 + 3000 certificats |
| 7 | comparer natif et Python sur la **même grammaire acceptée** | **vérifié, avec une divergence attendue** | parité tenue, sauf au-delà de la limite 64 variables |
| 8 | traiter CI, soundness, reproductibilité et performance réelle comme conclusions séparées | **respecté** | aucune de mes conclusions ne dérive d'une CI verte |

---

## 3. Point 3 en détail : trois opérations distinctes

La checklist demande de ne pas confondre trois choses. Mesures :

| opération | canal inconditionnel | instrument |
|---|---|---|
| `HMR` sur ancilla **prouvée** `\|0⟩` | **identique à l'identité** (gardée et tracée) | — |
| `reset(q)` (CPTP arbitraire) | `\|0⟩⟨0\|` quelle que soit l'entrée | **aucun slot** → non observable |
| `HMR(q, "bN")` | `\|0⟩⟨0\|` — **identique au reset** en canal | slot `bN` observé |

Conséquence importante : **`reset` et `HMR` sont le même canal inconditionnel.** La différence n'existe
que dans l'instrument. Un vérificateur qui compare des canaux ne peut donc pas les distinguer — et c'est
correct, pas un défaut. `same_instrument(reset, hmr, observed_slots=("b0",))` est **refusé**
(`observed classical slot not initialized`), ce qui est la bonne réponse : l'instrument n'est pas défini
d'un côté.

Deux HMR avec des slots nommés différemment (`b0` vs `b1`) : canal identique (`True`), et toute
observation est **refusée** des deux côtés plutôt que traitée comme égale. Fail-closed correct.

---

## 4. Point 4 : dix mutations de sémantique hybride

| mutant | verdict attendu | obtenu |
|---|---|---|
| bascule de condition (`b0` → `!b0`) | différent | **différent** |
| suppression du `X` conditionnel | différent | **différent** |
| canal identique, enregistrement observé différent | égal en canal, différent en instrument | **exactement cela** |
| slot écrasé avant usage (bit classique périmé) | différent en instrument | **différent** |
| `reset` vs `HMR` | égal en canal | **égal** |
| #94 : réparation annule la phase en `m` | dette supprimée | `{0b1011}` → `{}` |
| #94 : correction retirée | dette réapparaît | **réapparaît** |
| #94 : reçu face à un programme muté | refus | **`ValueError`** |

`10/10` conforme.

---

## 5. Point 5 : sept mutations de transcript

Les circuits sont **épinglés une fois** depuis le transcript légitime, puis tenus fixes pendant qu'on
mute le transcript — sinon une mutation régénère simplement des circuits cohérents et devient invisible.
C'est l'erreur que ma première version du harnais commettait, et je la signale parce qu'elle est facile à
reproduire.

| mutant | raison du refus |
|---|---|
| préfixe commun muté | `TranscriptMismatch: does not cover both complete streams` |
| suffixe commun muté | idem |
| embedding local remappé | idem |
| fil préservé non restauré | `UnprovedSubstitution: does not restore its preserved wires` |
| hash source épinglé faux | `TranscriptMismatch: hash mismatch` |
| flux candidat muté | `TranscriptMismatch` |

`7/7` conforme. Les trois premiers sont rejetés par le **même** garde (reconstruction des deux flux),
ce qui est le mécanisme voulu et non une coïncidence.

---

## 6. Point 6 : épuisement ANF `n ≤ 5`

Balayage exhaustif de **9 601 448 paires** (tous les ensembles de monomiales de taille ≤ 2, pour
`n` de 1 à 5 et `deg` de 0 à 3) :

| n | deg | paires | exacts | refus corrects (hors espace) | refus **évitables** |
|---:|---:|---:|---:|---:|---:|
| 2 | 1 | 64 | 38 | 24 | 2 |
| 3 | 2 | 4 096 | 1 052 | 1 928 | 1 116 |
| 3 | 3 | 8 649 | 8 649 | 0 | 0 |
| 4 | 2 | 53 824 | 3 414 | 44 996 | 5 414 |
| 4 | 3 | 331 776 | 70 858 | 154 432 | 106 486 |
| 5 | 3 | 8 714 304 | 345 594 | 7 524 600 | 844 110 |

**Total : 439 306 exacts, 8 188 826 refus corrects, 973 316 refus évitables (10,1 %), 0 résultats faux.**

### Correction d'un chiffre de mon rapport précédent

J'avais écrit « **61,3 %** des produits valides refusés ». Ce chiffre était exact **pour `n=4, deg=2`
seulement** et je l'ai présenté sans assez l'ancrer. Le chiffre global, sur tout le domaine épuisé, est
**10,1 %**. La formulation correcte est donc : *le taux de refus évitables dépend fortement de `n` et
`deg` (de 0 % à 32 %), avec 10,1 % de moyenne sur le domaine balayé*.

Ce qui ne change pas : **la direction de l'erreur est toujours le refus**, jamais une valeur fausse.

---

## 7. Point 7 : parité de grammaire native / Python

**250 programmes aléatoires** sur la grammaire acceptée, avec identités d'événement fraîches :

```
both accepted          : 250
both rejected          : 0
acceptance-split       : 0
verdict disagreements  : 0
GRAMMAR PARITY: HOLDS
```

Parité de **rejet** testée séparément sur des programmes hors grammaire (`reset`, `h`, outcome dupliqué,
`mcz_if` sans `hmr`) : les deux backends rejettent avec la même classe d'exception.

### Une divergence réelle, attendue et correcte

| `data` | `2·data` | `zdd` | `zdd-native` |
|---:|---:|---|---|
| 31 | 62 | accepte | accepte |
| 32 | 64 | accepte | accepte |
| 33 | 66 | **accepte** | **`ResourceLimitExceeded`** |

C'est la limite documentée (`README.md` ligne 22 : « the native 64-bit variable mask therefore requires
`2*n_data<=64` »). **Ce n'est pas un défaut de soundness** : la limite lève, elle ne renvoie jamais
`equivalent=False`. Un appelant qui capture large pourrait néanmoins confondre « ressource épuisée » et
« non équivalent » ; c'est une préoccupation d'API, pas de correction.

---

## 8. Ressources manquantes — signalement précis

La mission demande de signaler les ressources absentes plutôt que de supposer leurs résultats validés.
État vérifié le 29 octobre 2026 :

| ressource | état | conséquence |
|---|---|---|
| dépôt `yoch/qant` | **`gh api` → 404**, inaccessible depuis cet environnement | aucun chiffre qant n'est vérifiable ici |
| fixtures qant dans SymQ | **aucune** — `git ls-tree` sur `af8a874` ne contient aucun chemin `qant` | conforme à la règle AGENTS.md « no private fixtures » |
| corpus HMR réel redistribuable | **absent** de la PR #96 et des cinq PR | #95 n'est mesuré que sur des familles synthétiques |
| fragments produits par un compilateur | **absents** | #92 n'est démontré que sur mes exemples MAC |
| schéma d'entrée/sortie des fixtures qant | **non spécifié** | impossible de construire un substitut conforme |

**Ce que cela interdit de conclure :** qu'une capacité quelconque améliore le bloc GF(2¹²) de qant, ou
qu'un fragment HMR réel se comporte comme les familles synthétiques. **Ce que cela n'interdit pas :** tout
ce qui figure dans ce rapport, qui porte exclusivement sur du code public et des fonctions spécifiées.

Je n'ai importé aucun fixture privé et je n'en ai pas fabriqué de substitut.

---

## 9. Ce que la PR #96 change à mes conclusions

**Rien sur le fond, mais elle améliore la traçabilité sur trois points :**

1. elle **épingle explicitement** `7a75f827…` comme SHA mesuré — c'était mon finding P2 sur #95, il est
   désormais adressé au niveau du dépôt ;
2. elle **documente** que le C/ZDD perd sur l'affine et gagne sur le non linéaire, ce qui est exactement
   le résultat négatif que je demandais de conserver ;
3. elle **interdit explicitement** de présenter les tests qant comme exécutés, ce qui ferme la porte à
   l'inférence la plus dangereuse de cet ensemble.

**Ce qu'elle ne fait pas :** elle ne fournit ni code, ni fixture, ni test. C'est une checklist, pas une
preuve. Elle ne change donc aucune qualification de la matrice.

---

## 10. Matrice inchangée

| PR | CORRECT | VALIDATED | REVIEWABLE | MERGEABLE | PRODUCTION-READY |
|---|---|---|---|---|---|
| #90 | oui | oui | oui | oui | non |
| #92 | oui | oui | oui | oui | non |
| #93 | oui (réserve : 10,1 % de refus évitables) | oui | oui | oui | non |
| #94 | oui | oui | oui | oui | non |
| #95 | oui | oui | oui | oui | non |
| #96 | — (documentation) | n/a | oui | oui | n/a |

Les huit points de la checklist #96 sont **tous couverts par une preuve indépendante** dans ce dépôt.
Aucune qualification ne change : la vérification supplémentaire n'a révélé **aucun défaut de soundness
supplémentaire**, et a affiné un chiffre (10,1 % au lieu de 61,3 % présenté comme global).

Aucune fusion.
