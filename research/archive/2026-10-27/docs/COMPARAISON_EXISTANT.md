# Évaluation expérimentale comparative — version gelée du 27/10/2026

## Ce qui est réellement comparé

Sur les **11 circuits de référence publique QCEC** de la table `corpus/qcec_packed.tsv`, le même programme logique est exécuté par :

- `qant_set` : représentation ANF par `set[int]` comparable au traitement symbolique existant dans `experiments/dqi/gf_product_certificate.py`. Ce **n'est pas** un lancement du programme de certification natif qant.
- `fast_set` : même représentation, XOR de fil par `symmetric_difference_update` en place ; ne change pas l'algorithme.
- `adaptive` : ANF combinadic degré 2 puis repli sparse exact à dépassement de degré ; généralement non compétitif.
- `packed_only` : ANF combinadic degré 2 sans repli ; refus attendu dès degré 3 (pas de fausse preuve).
- `zdd` : diagramme de décision zero-suppressed canonique écrit en **Python dans ce paquet**. La technique remonte au moins à PolyBoRi (2009), mais ce n'est ni PolyBoRi C++ ni CUDD.
- `auto_zdd` : `fast_set` puis bascule irréversible vers `zdd` si ≥850 monômes après une porte non linéaire, ou si un produit dépasse la limite du sparse. Le choix du seuil a été examiné sur les 5 premiers circuits ; 6 autres forment un contrôle hors échantillon.
- `truth` : vecteurs bitset des valeurs sur **tout le cube booléen**, utilisables ici pour ≤18 variables libres. Cette méthode déjà pratiquée dans qant gagne sur les très petits domaines et devient exponentielle en mémoire.

**Aucun moteur tiers natif n'a été installé ni chronométré** dans ce conteneur : ni `mqt.qcec`, ni PolyBoRi ni Irene. Comparer directement leurs secondes aux chiffres ci-dessous serait scientifiquement invalide : leurs problèmes, langages et implémentations ne sont pas appariés.

## Protocole

- Python 3.13.5, Linux x86_64, AMD EPYC 9V74, conteneur exposant 5 CPU, ~5,9 Gio RAM ; résultat non normalisé CPU.
- Médianes de 7 exécutions, une instance à la fois ; chronométrage `perf_counter` **sans instrumentation**. Le pic d'allocation Python par `tracemalloc` est un second run indépendant non chronométré.
- Différentiel exact entre les représentations ANF sur **tous les n bits d'entrée symboliques** ; contrôle par tables de vérité exhaustives sur les domaines de 10 bits dans les tests, et vérification exhaustive/sous-échantillonnée lorsque `truth` est exécuté dans les benchmarks.
- Les microtemps <1 ms sont sensibles au bruit de scheduling, GC, caches CPU et fréquence ; pas de prétention d'intervalle de confiance.
- La preuve d'équivalence compare les fonctions classiques et le ledger de phase **dans le modèle annoncé**, non un circuit quantique général.
- Données : `results/bench_public_final_v3.json` (44 cas), `results/selector_sensitivity.json`, tests `tests/test_symbolic.py` et `tests/test_legacy_anf.py`.

## Résultat principal sur les circuits COMPLETS

| Circuit | Source ANF set (ms) | set en place (ms) | ZDD Python (ms) | AutoZDD (ms) | Bascule |
|---|---:|---:|---:|---:|---|
| `c2_181` | 226,04 | 209,49 | **0,835** | **2,276** | porte 33 |
| `mod5adder_306` | 0,173 | **0,146** | 1,124 | 0,179 | aucune |
| `rd73_312` | 0,205 | **0,137** | 1,304 | 0,150 | aucune |
| `rd84_313` | 0,382 | **0,299** | 2,317 | 0,321 | aucune |
| `sym9_317` | 0,532 | **0,309** | 2,389 | 0,310 | aucune |
| `5xp1_194` (test) | 0,212 | **0,173** | 0,764 | 0,202 | aucune |
| `alu1_198` (test) | 0,046 | **0,039** | 0,195 | 0,048 | aucune |
| `dk27_225` (test) | 0,066 | **0,063** | 0,185 | 0,073 | aucune |
| `cm150a_210` (test) | 0,198 | **0,117** | 0,605 | 0,134 | aucune |
| `pcler8_248` (test) | 0,042 | **0,036** | 0,169 | 0,044 | aucune |
| `mlp4_245` (test) | 0,434 | **0,302** | 1,509 | 0,342 | aucune |

Les chiffres sont arrondis pour lecture ; les valeurs exactes figurent dans le JSON.
**Sur `c2_181`, AutoZDD est ≈99× plus rapide que l'ANF set, et ZDD pur ≈271×.** Ce cas pathologique est l'unique point de gros bénéfice du corpus. Son pic d'allocation Python passe de 5 040 168 octets (sparse) à 498 208 octets (AutoZDD), soit ≈10,1× moins ; ce n'est pas le RSS OS. L'ANF sparse y porte 8 520 monômes vivants ; le backend ZDD alloue environ 400 nœuds partagés.

Sur **les 10 autres**, la médiane des gains `fast_set`/`qant_set` est d'environ **1,25×**. Le ZDD pur est en médiane ≈5,1× *plus lent* que `fast_set`. Le sélecteur évite cette dégradation, mais son wrapper peut coûter quelques dizaines de µs : **ne pas promettre un gain universel**.

### Sensibilité et contrôle hors échantillon

- Le seuil 850 n'a déclenché **aucun ZDD inutile sur les 6 circuits réservés** ; leur maximum local après une porte non linéaire est ≤164 monômes.
- Sur les 5 exemples de développement, le maximum hors cas `c2_181` est 525 monômes ; 850 conserve la représentation sparse. Un seuil 100 déclenche sur plusieurs cas faciles et les ralentit.
- Dans `c2_181`, 850 déclenche à la porte 33. À 1200 monômes, la bascule vient à la porte 35, avec une conversion beaucoup plus coûteuse ; les résultats de timing montrent ≈11 ms contre ≈2,5 ms (cette comparaison de seuils est un scan expérimental, pas un théorème de sélection optimale).
- Un seul cas difficile ne constitue pas une estimation statistique de vitesse moyenne sur l'industrie. Il faut élargir le corpus.

## Résultat des fragments synthétiques GF(2¹²) / HMR

- `GF12_SYNTH/echo_10000`, environ 20 000 CX réversibles rajoutés : `qant_set` **15,36 ms**, `fast_set` **7,85 ms**, `auto_zdd` **10,51 ms**, `zdd` **15,65 ms**.
- Il s'agit d'une construction algébrique et de mesure **synthétique** (pas du vérificateur Kickmix réel). Ces portes neutres servent à profiler le coût par instruction sans apporter de nouveauté logique.
- Les résultats récents sans `tracemalloc` ont corrigé une surestimation des gains packed tirée des tests instrumentés antérieurs.

## Résultats négatifs essentiels

1. `packed_only` ne traite qu'une partie des cas (11/44) ; sur les autres, il échoue explicitement sur des monômes de degré >2.
2. `adaptive` à démotions fréquentes peut être plus lent que `fast_set` — le coût de bascule de représentation n'est pas gratuit.
3. `ZDD` pur est un mauvais défaut sur les petites formules peu denses.
4. La compression factorisée du polynôme de phase GF(2¹²) (~397× sur la seule structure ANF cible dans le laboratoire antérieur) ne prédit pas un gain RSS ou temps sur le certificat natif entier.
5. Les conclusions ne concernent ni un score Kaggle, ni un gain en Toffoli/Q, ni une amélioration du solveur global.

## Comparaison scientifique externe

**PolyBoRi (2009)** utilise des ZDD pour les polynômes booléens : notre performance sur `c2_181` illustre précisément l'intérêt bien connu de partager les sous-structures combinatoires. Ce résultat seul n'est pas une découverte publiable.

**MQT QCEC** utilise entre autres diagrammes de décision, réécritures ZX et simulation pour comparer des circuits quantiques généraux. Ici, nous ne mesurons **que nos représentations** sur quelques circuits tirés de sa collection de tests ; nous n'avons ni lancé son checker ni évalué son temps de preuve.

**Irene (2026)** annonce 1 584/1 982 paires équivalentes ou non résolues par ses méthodes HPS/densité/SMT ; notre objectif est plus étroit (reversibilité classique, phases ± et mesure X sous contrat), et nos 11 circuits n'établissent aucune supériorité comparée.

**Verdict publication :** résultat d'optimisation d'outil intéressant et reproductible. Une étude scientifique solide exige davantage de circuits 2026 réels avec HMR, un vrai comparateur PolyBoRi/CUDD/QCEC exécuté dans les mêmes conditions, et une politique de sélection validée à l'aveugle sur plusieurs familles. Ne pas annoncer de nouveauté théorique avant ces étapes.
