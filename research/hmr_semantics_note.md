# Note sémantique — fragment HMR de SymQ

Document de référence pour l'issue #72. Il décrit ce que le fragment accepte réellement, ce qu'il
garantit, et ce qu'il ne prétend pas.

## Fragment accepté

Instructions : `mcx` (X/CX/CCX/MCX), `mcz` (Z/CZ/CCZ), `hmr` (mesure en base X suivie d'une remise
à zéro) et `mcz_if` (correction classique conditionnée par une issue antérieure).

**Phases ±1 uniquement.** Chaque porte de phase multiplie par `(-1)^p` où `p` est un polynôme
booléen. Il n'y a ni racine 8-ième de l'unité, ni porte `S` ou `T`, ni phase complexe. La sémantique
est de l'arithmétique exacte sur GF(2) ; la docstring du module affirmait `Z_8`, c'était faux et
c'est corrigé.

## Sémantique

Un programme définit, pour chaque fil, une fonction booléenne `f_w` des entrées `x`, et une phase
`phi(x, m)`. Les valeurs de fils ne dépendent jamais des issues `m` ; seule la phase en dépend, et
elle y est **affine** : `phi = phi0(x) + sum_j m_j g_j(x)`.

## Obligations

- **O1** : toute ancilla revient à `0`.
- **O2** : la phase ne dépend d'aucune issue.

Un programme qui satisfait O1 et O2 définit une transformation unitaire sur les fils de données.

## Trois notions distinctes, à ne jamais confondre

| notion | ce qu'elle compare | qui la décide |
|---|---|---|
| égalité branche par branche | `f` et `phi(x, m)` pour tout `m` | `check_phase_equivalence` (critère strict) |
| égalité à un signe global près | idem, à `phi` près d'une constante | idem, champ `up_to_global_phase` |
| égalité de canaux | `E(rho)` après somme sur les issues | `factored.equivalent_channel`, vérifié par `channel.py` |

Le critère de canal est **strictement plus faible** que O2 : il accepte des programmes dont la
phase dépend des issues mais dont le canal est inchangé. Il ne remplace pas le critère strict.

## Oracle

`src/symq/phase_oracle.py` (vecteur d'état) et `research/innovation/2026-10-28/prototype/channel.py`
(matrice de densité exacte) sont indépendants du vérificateur : ils ne partagent aucun code avec
`phase.py` et n'utilisent ni ANF ni espace de paires. Tout témoin renvoyé par le critère est
revérifié contre eux.

## Hors périmètre

Portes quantiques générales, phases non réelles, mesures dans d'autres bases, mises à jour de
données conditionnées par une issue, correction multi-issues. Aucun résultat de ce module ne
constitue une vérification quantique générale.

## Limite connue

Une différence de **noyau** (les fonctions `g` diffèrent) n'a pas de témoin `(x, y)` : le verdict
l'indique par `kernel_differs` sans fabriquer de coordonnées. C'est documenté plutôt que masqué.
