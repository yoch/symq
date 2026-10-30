# Deuxième passe — archive absente, kit public #98, gadget multi-dettes #94

**SHA audités :** #94 `ddd64606693042259fa76e1fe39dc161b0e34bcd` · #98 `9d0e0a3546d152ec3aa5ad79d1f582c7997bd4d3` · #97 `8150759a1cdb77fbb0d62c656b2ab81115aff0c9`

---

## 1. Archive externe v2 : `ARCHIVE_NOT_AVAILABLE`

La mission annonce deux fichiers joints : l'archive de référence externe v2 et un rapport privé. **Les
deux sont absents de cet environnement.**

Recherche exécutée avant toute autre opération :

| recherche | résultat |
|---|---|
| `find / -iname "*audit_bundle*v2*" -o -iname "*reference*v2*" -o -iname "*bundle*20261029*"` | **0** |
| `find / -name "*.zip"` filtré (hors polices/toolchains) | aucun bundle |
| fichiers créés depuis 10:40 le 29/10 (archives, rapports) | uniquement des `REPORT.md` déjà présents dans les worktrees |
| uploads de session | 8 fichiers du 27/10, aucun nouveau |
| stores d'agent, points de montage, catalogue d'outils dynamiques | rien |

**Conséquence** : les 65 fichiers annoncés, le `README_FOR_AGENT.md`, `MANIFEST.json`, `SHA256SUMS` et
le commit `040baca3…` restent **non vérifiés**. Le point de contrôle « 113 réussites, 28 ignorés » **ne
peut pas être reproduit** sans l'archive — je ne le confirme ni ne l'infirme.

**Aucun substitut n'a été fabriqué.** Aucun fixture privé n'est copié.

Ce que cela n'empêche pas : tout ce qui suit porte sur du **code public**, et la question la plus
importante de cette passe — le gadget multi-dettes de #94 — se tranche entièrement sans l'archive.

---

## 2. Kit public #98 — vérifié

PR #98 fournit une ressource publique autonome (3 fichiers, 229 lignes). Je l'ai exécutée.

| vérification | résultat |
|---|---|
| `pytest tests/test_public_qualification.py` | **2 passed** |
| oracles `--degree 2` / `--degree 3` | **exécutés**, rapports produits avec `report_sha256` |
| aucune dépendance externe (ni import, ni `sys.path`) | **conforme** — test `test_the_public_kit_supplies_no_private_payload` |
| CI sur `9d0e0a3` | **7/7** |

**Ce que le kit est** : un oracle de champ GF(4)/GF(8) reconstruit indépendamment, stdlib-only, avec
somme exacte des signes de Kraus sur `|x⟩⟨y|`. **Ce qu'il n'est pas** : un fragment authentifié de
compilateur. Son README le dit explicitement, et je le confirme — c'est une reconstruction déclarée
comme telle, catégorie 3 de la taxonomie de provenance (« exemple synthétique inspiré d'un
algorithme »), pas catégorie 1.

Le kit annonce aussi que #97 « peut explicitement sauter des tests si le réseau est indisponible » et
que « un job vert avec des sauts partiels n'est pas une validation indépendante complète ». **C'est
exact**, et c'est précisément pourquoi j'ai ajouté un garde CI qui échoue si rien ne s'exécute.

---

## 3. PR #94 au nouveau commit — deuxième famille de tests

### Le gadget

Multiplication-accumulation en corps de Galois, trois registres de `degree` bits (A, B, accumulateur C)
plus `degree` ancillas produit. Le produit brut est calculé par convolution polynomiale et réduction,
plié dans C, puis **chaque bit produit est HMR'é** — ce qui laisse **une dette de phase par bit**.

| degré | largeur | données | ancillas | mesures | corrections synthétisées |
|---:|---:|---:|---:|---:|---:|
| GF(2²) | 8 | 6 | 2 | 2 | **5** |
| GF(2³) | 12 | 9 | 3 | 3 | **12** |

C'est bien une **deuxième famille** : dettes multiples, plusieurs événements, sorties multiples.

### Ce que sa propre suite vérifie

`tests/test_hmr_field_mac_research.py` — **3 passed**. Elle énumère toutes les entrées et toutes les
issues via `run_program`, et compare à un multiplieur de corps entier indépendant. Solide, mais
**uniquement sur les branches de base**.

### Ce que j'ai ajouté, et qui manquait

**Vérification hors diagonale avec l'oracle CPTP de #90** — la propriété qu'une revendication de canal
exige réellement :

| vérification | GF(4) |
|---|---|
| corrigé == référence, **canal complet** (ancilla gardée) | **`True`**, 4096 paires |
| corrigé == référence, **ancilla tracée** | **`True`** |
| non corrigé == référence | **`False`** |

C'est le premier contrôle de ce gadget **au niveau canal** et pas seulement au niveau des branches. Il
passe.

GF(8) est de largeur 12 : `(2^9)² = 262 144` paires, hors de portée de l'oracle exponentiel. J'ai donc
échantillonné un **sous-espace cohérent** : **240 vérifications unité/mode, 0 écart**.

### Mutants — 13 corrections balayées, pas seulement la première

La suite de la PR retire **une** correction à un indice fixe. J'ai balayé **toutes** :

| mutant | résultat |
|---|---|
| retirer la correction #0, #5, dernière | `False` — O2 violé (1 monomiale résiduelle) |
| retirer **chacune** des 12 corrections de GF(8), une par une | **toutes détectées** |
| échanger un contrôle | `False` — O2 (2 monomiales) |
| décaler l'index d'issue | `False` — O2 (2 monomiales) |
| retirer toutes les corrections | `False` — O2 (12 monomiales) |

**Aucune correction n'est redondante.** C'est plus fort que ce que la PR démontrait.

### Reconstruction indépendante, pas un import

J'ai **réécrit** le constructeur du gadget depuis sa description plutôt que d'importer le module de
test de la PR. Un test `test_the_reconstructed_gadget_matches_the_prs_own_builder` vérifie que ma
reconstruction produit **exactement** la même liste d'opérations que la leur, sur GF(4) et GF(8). Sans
ce contrôle, toutes mes conclusions porteraient sur ma reconstruction et non sur la PR.

### Statut `KEEP_EXPERIMENTAL` — réévalué

**Il est levé.** La raison invoquée était : « le seul gadget démontré est `x0∧x1` sur une ancille
temporaire, cas que la vérification directe traite déjà ». Ce n'est plus vrai :

- le gadget est un **multiplieur de corps complet**, à sorties multiples ;
- il porte **2 puis 3 dettes simultanées** sur des événements distincts ;
- il exige **5 puis 12 corrections** combinées ;
- il est vérifié **au niveau canal**, hors diagonale ;
- chaque correction est **individuellement nécessaire et individuellement détectable**.

C'est exactement le « second gadget non trivial » dont je disais qu'il suffirait à changer la décision.

**Nouvelle décision : `MERGE_RESEARCH`.**

Ce qui reste hors périmètre, et n'est donc pas revendiqué : l'optimalité du nombre de portes
(`_elimination` reste glouton), et l'application à un fragment HMR réel de compilateur.

---

## 4. Point 3 de la mission — 36 bits cohérents et la limite native 64

Trois registres de 12 bits = **36 fils cohérents**. L'encodage natif apparié utilise `2·data`
variables, donc **72 > 64**.

| data | 2·data | backend `zdd` | backend `zdd-native` |
|---:|---:|---|---|
| 32 | 64 | décide | décide |
| 33 | 66 | décide | **`ResourceLimitExceeded`** |
| 36 | 72 | **décide** | **`ResourceLimitExceeded`** |

**La précondition est rejetée, pas supposée.** Aucun verdict n'est rendu pour un contrat que le moteur
natif ne peut pas représenter — le test `test_native_backend_rejects_a_36_bit_coherent_contract` le fige.

**Nuance importante pour le plan d'intégration** : la limite est **représentationnelle, pas
sémantique**. Le backend Python `zdd` **décide** le contrat 36 bits
(`test_the_pure_python_backend_still_decides_the_36_bit_contract`). L'énoncé honnête est donc :

> un contrat GF(2¹²) à 36 bits cohérents **n'est pas supporté par le chemin natif** ; il reste
> **décidable par le chemin Python**, ou doit être traité par un théorème de composition sur
> sous-espace.

Ce n'est **pas** « non supporté ». La distinction compte : elle interdit de conclure que #95 est
inutilisable pour la cible GF(2¹²), et elle interdit symétriquement de supposer que le natif y apporte
un gain.

---

## 5. Statut de la PR #98

`MERGE_RESEARCH`. Documentation et oracle autonome, sans code privé. Son README est **exact** sur ses
propres limites, y compris la mise en garde contre l'interprétation d'un job vert partiel. Je n'y ai
trouvé aucune revendication excessive.

Un point de forme : le kit ne peut pas remplacer l'archive absente. Il fournit une **reconstruction
déclarée**, pas les fixtures historiques. La ligne « #97 : evidence bound to local source
availability » est correcte.

---

## 6. Décisions mises à jour

| PR | Décision précédente | Décision maintenant | raison du changement |
|---|---|---|---|
| #90 | `MERGE_RESEARCH` | `MERGE_RESEARCH` | inchangé |
| #92 | `MERGE_RESEARCH` | `MERGE_RESEARCH` | inchangé |
| #93 | `MERGE_RESEARCH` | `MERGE_RESEARCH` | inchangé |
| #94 | `KEEP_EXPERIMENTAL` | **`MERGE_RESEARCH`** | **second gadget non trivial, multi-dettes, vérifié au niveau canal** |
| #95 | `MERGE_RESEARCH` | `MERGE_RESEARCH` | inchangé ; limite 36 bits précisée |
| #96 | `MERGE_RESEARCH` | `MERGE_RESEARCH` | inchangé |
| #97 | `MERGE_RESEARCH` | `MERGE_RESEARCH` | cette passe ajoute 11 tests |
| #98 | — | **`MERGE_RESEARCH`** | kit public exécuté, limites exactes |

**Aucune promotion en API de production.** L'obstacle reste le même pour toutes : aucune donnée réelle
redistribuable. L'archive qui devait la fournir est absente, et #98 fournit une reconstruction
explicitement déclarée, ce qui n'est pas équivalent (catégorie 3, pas catégorie 1).

---

## 7. Reproductibilité

`tests/test_public_qualification_audit.py` — **11 tests**, ~1,3 s, exécutés en CI.

Épinglés : #90 `38a1372`, #94 `ddd6460`, #95 `af8a874`, #98 `9d0e0a3`. Chaque test *fetch* son commit
et **skip avec motif** s'il est inatteignable.

**Mutation-testé** : en faisant que le synthétiseur n'ajoute aucune correction, **5 tests échouent**.
La suite détecte donc réellement l'absence de réparation.

Le bug d'import que j'ai rencontré (le paquet `research` résolvait vers mon dépôt, pas vers le
worktree) est documenté dans le helper `_import_from`, et contourné pour le gadget par une
**reconstruction indépendante** plutôt qu'un import — ce qui est de toute façon la meilleure méthode
d'audit.
