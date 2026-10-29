# Plan d'intégration — décisions par PR

**Base : `yoch/symq` `main`. Tous les HEAD revalidés le 29 octobre 2026.** Aucune fusion effectuée.

## Décisions

| PR | Décision | Fusion prototype de recherche | Promotion en API de production |
|---|---|---|---|
| **#90** | `MERGE_RESEARCH` | oui, sous `research/` | **non** — oracle exponentiel borné à 6 fils |
| **#92** | `MERGE_RESEARCH` | oui, sous `research/` | **non** — permutations classiques seulement |
| **#93** | `MERGE_RESEARCH` | oui, sous `research/` | **non** — pas de gain mesuré indépendamment |
| **#94** | **`MERGE_RESEARCH`** | **oui** (révisé le 29/10) | non |
| **#95** | `MERGE_RESEARCH` | oui, sous `research/` | **plus tard**, sous conditions mesurées |
| **#96** | `MERGE_RESEARCH` | oui (documentation) | n/a |
| **#98** | `MERGE_RESEARCH` | oui (kit public) | n/a |
| **#97** | `MERGE_RESEARCH` | oui (rapports + harnais) | n/a |

**Distinction essentielle** : « fusion d'un prototype de recherche » signifie que le code entre dans
`main` **sous `research/`**, avec ses limites documentées, sans contrat d'API stable et sans promesse de
maintenance. « Promotion en API de production » signifie qu'il sort de `research/`, gagne un contrat
public, des tests de non-régression et des budgets de ressources — c'est une décision séparée, et
aucune PR ne la mérite aujourd'hui.

---

## #90 — Oracle CPTP hybride

**Prouvé.** Exact sur son périmètre : 24/24 cas construits à la main et 120 programmes aléatoires,
accord **exact** avec une référence indépendante (matrices denses, familles de Kraus) sur toutes les
unités `|x⟩⟨y|`, ancillas gardées et tracées. Le piège `CX;reset` est correctement rejeté là où un
vérificateur par diagonale seule accepterait. `same_channel` et `same_instrument` sont réellement
distincts et fonctionnent.

**Inconclusif.** Rien sur un circuit de taille réelle : l'oracle est en `(2^data)²` unités × matrices
`2^(data+anc)`. Aucune comparaison à un autre vérificateur sur un cas non trivial.

**Bloquant pour la production.** Complexité exponentielle assumée ; borne `max_width=6`, `max_events=8`.

**Couverture gagnée par l'archive.** Aucune : archive absente (`ARCHIVE_NOT_AVAILABLE`).

**Potentiel de performance.** Nul et non recherché — c'est un oracle de référence.

**Code natif.** Sans objet.

**Conditions minimales pour sortir de `research/`.** Aucune raison de le faire : sa valeur est d'être
l'oracle contre lequel les moteurs scalables se valident. Le garder sous `research/` est le bon statut
permanent.

---

## #92 — Substitution temporelle

**Prouvé.** `check_equivalence` est **total sur tous les fils**, propriété dont dépend l'induction. 200
transcripts à deux slots chevauchants : aucun faux positif, tous vérifiés globalement égaux par
énumération. Transcripts liés (hash, couverture des deux flux). Second exemple connecté : largeur 50–70,
un seul bloc, preuve locale plate à 0,4–0,9 ms quand le moniteur monolithique passe de 0,2 à 17,4 ms.

**Inconclusif.** Aucun circuit issu d'un compilateur réel. Aucune analyse de phase ni de mesure — c'est
hors périmètre et documenté.

**Bloquant pour la production.** Périmètre purement classique ; le hash est fourni par l'appelant, qui
peut le calculer depuis l'entrée non fiable qu'il prétend authentifier.

**Couverture gagnée par l'archive.** Aucune.

**Potentiel de performance.** **Le seul gain de coût mesuré et favorable de l'ensemble**, sur un cas
connecté reproductible.

**Code natif.** `backend="zdd-native"` possible par slot, jamais sur le flux global (limite 64 fils).

**Conditions minimales pour sortir de `research/`.** (a) un circuit de compilateur réel ; (b) une API
qui prenne hash et circuit **séparément obtenus** ; (c) nommer le périmètre `classical` dans l'API.

---

## #93 — ANF combinadique, domaines finis, certificats GF(2)

**Prouvé.** Bijection colex exhaustive (`variables` 1..6, `degree` 0..4), sans collision. Certificats
duaux GF(2) exacts (5036 systèmes exhaustifs + 3000 aléatoires, accord parfait avec la force brute).
ANF : **9 601 448 paires, 0 résultat faux**.

**Inconclusif / reclassé.** Le refus des produits à monomial intermédiaire hors degré n'est **pas un
défaut** : l'issue #86 l'exige (« never issue a proof from a truncated polynomial »). Mon balayage en
**mesure le coût** : 10,1 % de refus évitables sur `n ≤ 5`, jusqu'à 32 % localement.

**Bloquant pour la production.** Aucun gain de performance mesuré indépendamment ; la limite de degré
réduit la couverture.

**Couverture gagnée par l'archive.** Aucune.

**Potentiel de performance.** Non démontré. Le benchmark de la PR n'a pas été reproduit.

**Code natif.** Aucun ; arithmétique bigint Python.

**Conditions minimales pour sortir de `research/`.** Reproduire le benchmark sur une famille utile et
montrer un gain **complet** (temps d'appel public, RSS) contre `sparse`/`packed`/`zdd`.

---

## #94 — Réparation de dettes de phase HMR

**Prouvé.** La dette est annulée exactement : `phase_semantics` passe de `{0b1011}` à `{}`, sorties
inchangées. 150 programmes aléatoires : 58 réparés, 92 refusés, **0 incorrect**. **Interopérable avec
#90** : 17/17, dont le gadget canonique égal au circuit de valeur en canal complet et tracé.

**Inconclusif.** Aucun gadget réaliste distinct du AND temporaire. Les corrections ne sont pas optimales
en nombre de portes (`_elimination` est déterministe, pas un minimiseur). Aucune mesure de coût.

**Bloquant pour la production.** Utilité pratique non démontrée : le seul exemple est `x0∧x1` sur une
ancille temporaire, cas que `check_phase_equivalence` traite déjà sans synthèse.

**Couverture gagnée par l'archive.** Aucune.

**Potentiel de performance.** Aucun revendiqué, aucun mesuré.

**Code natif.** `audit_backend="zdd-native"` vérifie les équations booléennes, pas le canal.

**Décision révisée le 29 octobre 2026 : `MERGE_RESEARCH`.**

Le motif du `KEEP_EXPERIMENTAL` était « le seul gadget démontré est `x0∧x1` sur une ancille temporaire ».
Le commit `ddd6460` lève cette objection avec un **multiplieur de corps GF(4)/GF(8) à sorties
multiples** : 2 puis 3 dettes simultanées, 5 puis 12 corrections, vérifié **au niveau canal** (4096
paires hors diagonale en GF(4), sous-espace cohérent en GF(8)), et **chaque correction individuellement
nécessaire** — les 12 retraits un par un sont tous détectés.

Restent hors périmètre et non revendiqués : l'optimalité du nombre de portes (`_elimination` est
glouton) et l'application à un fragment HMR réel de compilateur.

---

## #95 — Vérificateur de canal natif C/ZDD

**Prouvé.** Identité de factorisation vérifiée contre un oracle indépendant : **312 unités, 0 écart**.
**60/60 verdicts** identiques entre le moteur natif et un moteur d'algorithme différent. Le chemin chaud
est réellement du C (**1261** appels `NativeZDDManager.product` contre 215 005 récursions Python).
Parité de grammaire sur 250 programmes. ASan/UBSan propre. Témoins rejoués par un interpréteur entier
indépendant.

**Inconclusif.** Aucune donnée issue d'un compilateur réel ; les quatre familles sont synthétiques.

**Bloquant pour la production.** Les mesures portent sur du synthétique ; la revendication « plus
rapide » doit être restreinte au non linéaire.

**Couverture gagnée par l'archive.** Aucune.

**Potentiel de performance.** **Le plus solide de l'ensemble** : 0,98× sur l'affine (donc neutre à
légèrement défavorable), **6,6×** et **2,4×** sur le non linéaire, stable à ±3 % sur trois exécutions.

**Code natif.** Réel, mesuré, profilé, ASan-propre. C'est la seule PR de l'ensemble qui le mérite.

**Contrat 36 bits (précisé le 29/10).** Trois registres de 12 bits exigent 72 variables appariées,
au-delà de la limite native de 64. La précondition est **rejetée**, jamais supposée. Mais la limite est
**représentationnelle, pas sémantique** : le backend Python `zdd` décide encore le contrat 36 bits. Un
contrat GF(2¹²) n'est donc pas « non supporté », il est « non supporté par le chemin natif ».

**Conditions minimales pour sortir de `research/`.**
1. un corpus **réel** redistribuable (absent) ;
2. restreindre la revendication au non linéaire, et **conserver** le résultat négatif affine ;
3. une API explicite qui distingue « ressource épuisée » de « non équivalent » — la limite 64 variables
   lève aujourd'hui `ResourceLimitExceeded`, ce qui est correct mais ambigu pour un appelant qui
   capture large ;
4. épingler le SHA mesuré (fait par #96).

---

## #96 — Checklist publique

Documentation pure, 32 lignes, aucun code. Liens et provenance vérifiés exacts. **`MERGE_RESEARCH`.**

## #97 — Audit indépendant

Rapports, harnais exécutables et suite pytest rejouable. **Contient une correction explicite d'une de
ses propres conclusions** (le P1 HMR retiré). **`MERGE_RESEARCH`.**

---

## Ordre d'intégration recommandé

Aucune dépendance technique entre les PR : chacune ajoute des fichiers isolés. L'ordre par valeur
démontrée, et par risque croissant :

1. **#96** et **#97** — documentation et audit, sans effet sur le code.
2. **#95** — la PR la plus solide, et la seule avec un gain de performance reproductible.
3. **#92** — composition saine et gain de coût mesuré sur circuit connecté.
4. **#90** — oracle de référence, à garder sous `research/` durablement.
5. **#93** — exact, mais sans gain démontré.
6. **#94** — en dernier, et seulement avec un gadget réaliste.

**Le seul point qui aurait bloqué une intégration a été levé** : le P1 « conventions HMR incompatibles »
était faux, et l'interopérabilité #90/#94 est démontrée. Il ne reste **aucun bloqueur de correction**
dans l'ensemble.

## Ce qui reste réellement bloquant pour la production

Un seul obstacle, partagé par toutes les PR : **aucune donnée réelle redistribuable**. L'archive qui
devait la fournir est absente (`ARCHIVE_NOT_AVAILABLE`), et le dépôt de référence est inaccessible
depuis cet environnement. Tant que ce point n'est pas levé, aucune promotion en API de production n'est
justifiable, quelle que soit la qualité du code.
