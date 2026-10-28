# Composition relationnelle — théorème local corrigé (issue #71)

> **PR [#77](https://github.com/yoch/symq/pull/77).** Ce document remplace la version auditée à
> `7e7b481`, qui annonçait une garantie universelle que le code ne démontrait pas. Voir
> [l'audit](https://github.com/yoch/symq/pull/77#issuecomment-6475752348).

**Décision : `KEEP` sur l'IR d'expressions et sur la règle à quatre obligations ; `EXPERIMENTAL` sur
le théorème de suffixe local (désormais prouvé, sur un exemple) ; `STOP` sur la thèse « composer coûte
moins cher ».**

---

## 1. Ce qui était faux

À `7e7b481`, l'obligation de suffixe encodait `A;B` et `A';B'` **avec les deux entrées initiales
liées** (`encoder.equiv(first, second)`), puis asserait `R` à la coupe interne. Elle ne démontrait
donc que

$$R(A(x),A'(x))\land Pre_B(A(x)) \Rightarrow post(B(A(x)),B'(A'(x)))$$

pour une entrée commune `x`, et non l'énoncé universel annoncé

$$\forall u,v:\quad R(u,v)\land Pre_B(u)\Rightarrow post(B(u),B'(v)).$$

C'est une vérification d'**états atteignables**, pas une preuve locale réutilisable : elle accepte dès
que les préfixes appariés rendent la conclusion vraie, même si `R` seul ne l'implique pas.

**Contre-exemple de l'audit, vérifié à la main et sans solveur.** `u = 0`, `v = 1` : les deux ont le
bit 2 nul, donc `R = (u.2 = v.2)` tient ; `Pre_B = TRUE` tient ; et pourtant `B(u) = 0` alors que
`B'(v) = 1`, donc `post` (égalité sur les fils 0,1,2) échoue. L'ancien vérificateur acceptait ce cas
parce que ses préfixes appariés imposaient implicitement l'égalité sur le fil 0.

Régression mesurée en chargeant l'ancien module séparément :

| relation | `7e7b481` | corrigé |
|---|---|---|
| `R = (u.2 = v.2)` | **accepted = True** | **accepted = False**, `suffix` SAT |
| `R` sur les fils 0,1,2 | — | **accepted = True**, `suffix` UNSAT |

---

## 2. La correction

`_suffix_obligation` n'encode plus que `suffix_left` et `suffix_right`. Leurs entrées sont deux
variables symboliques fraîches `u` et `v`, **sans aucune clause les liant** : leur seule relation est
`R`. Aucun préfixe n'apparaît dans la requête et `u`, `v` ne sont jamais identifiés.

| nom | requête | attendu |
|---|---|---|
| `domain` | `P(x)` | **SAT** — sinon tout le reste est vacueux |
| `prefix` | `P(x) ∧ ¬R(A(x), A'(x))` | UNSAT |
| `interface` | `R(u,v) ∧ ¬Pre_B(u)` | UNSAT |
| `suffix` | `R(u,v) ∧ Pre_B(u) ∧ ¬post(B(u), B'(v))` | UNSAT |

Seule `prefix` lie les deux blocs à une entrée commune ; c'est elle qui transforme le lemme local en
énoncé sur les circuits composés.

**Preuve structurelle** : faire grossir les préfixes laisse le CNF de `suffix` **identique** (mêmes
clauses, mêmes variables) tandis que celui de `prefix` grandit. C'est la vérification mécanique que
les préfixes ne sont plus encodés.

**Sûreté, en quatre lignes.** Pour tout `x` satisfaisant `P` : (1) donne `R(u,v)` aux états de coupe ;
(2) donne `Pre_B(u)` ; (3) quantifie sur **toutes** les paires satisfaisant `R ∧ Pre_B` et impose
`post` à leurs images. Par composition, `(A;B)(x)` et `(A';B')(x)` satisfont `post`. L'étape (3) est
universelle, donc l'argument n'a besoin d'aucune connaissance de la façon dont les préfixes atteignent
la coupe — c'est précisément ce qu'achète une preuve compositionnelle.

---

## 3. L'exemple de base

Largeur 4 : `A = CCX(0,1,2)`, `A' = A; X(3)`, `B = B' = CX(2,0)`.
`R` : égalité sur les fils 0,1,2 (le fil 3 libre). `Pre_B = TRUE`.

`A` et `A'` laissent des états de coupe **différents** (`x3` diffère pour toute entrée), donc aucune
égalité fil à fil ne peut les relier. Le test
`test_the_interface_relation_still_does_work_across_the_cut` vérifie qu'exiger l'égalité sur le fil 3
fait rejeter une composition correcte.

**Le fil 3 est du garbage, pas une ancilla restaurée.** `A' = A; X(3)` le laisse inversé pour toute
entrée, et le contrat l'ignore. Aucun test ne prétend le contraire ; supporter une vraie restauration
demanderait une obligation supplémentaire, non implémentée.

---

## 4. Un exemple où `Pre_B` est indispensable

`P : x0 = 0 ∧ x2 = 0` · `A = CCX(0,1,2)` · `A' = A; X(3)` · `B = identité` · `B' = CX(2,0)`
`R` : égalité sur les fils 0,1,2 **et** `u.2 = 0` · `Pre_B : u.2 = 0`

Les suffixes sont équivalents **sur le domaine de `Pre_B` seulement** : `B` et `B'` diffèrent dès que
`u.2 = 1`. Vérifications indépendantes : les quatre obligations passent ; `P` est non vide (8 entrées
sur 16) ; les circuits composés coïncident sur les fils observés pour toute entrée satisfaisant `P` ;
et `B`, `B'` **diffèrent** hors de `Pre_B`, donc la restriction fait un vrai travail.

Trois mutants, tous refusés :

| mutant | obligation qui échoue | témoin |
|---|---|---|
| `R` sans `u.2 = 0` | `interface` | paire `(4,4)` : `R` tient, `Pre_B` échoue |
| `Pre_B = TRUE` | `suffix` | paire dont les images diffèrent sur un fil observé |
| `B' = X(0)` | `suffix` | aucune restriction ne la sauve |

Remarque sur le second : avec la relation **complète** (qui contient déjà `u.2 = 0`), mettre
`Pre_B = TRUE` ne casse rien, puisque `R` force déjà la condition. Le mutant n'est probant qu'avec la
relation réduite — ce que le test utilise. C'est aussi pourquoi `R` et `Pre_B` restent deux
obligations distinctes.

---

## 5. Témoins réellement vérifiés

`replay_witness` ne se contente plus d'exécuter deux circuits. Chaque obligation est rejouée contre
**sa propre** sémantique :

- `domain` : l'entrée satisfait `P` ;
- `prefix` : l'entrée satisfait `P`, et `A(x)`, `A'(x)` violent `R` ;
- `interface` : la paire `(u,v)` satisfait `R` et viole `Pre_B` — **aucune entrée `x` n'est inventée** ;
- `suffix` : la paire `(u,v)` satisfait `R` et `Pre_B`, et l'exécution concrète de `B(u)`, `B'(v)`
  viole `post`.

Un témoin de coupe est une **paire**, qui n'est pas nécessairement atteignable depuis une entrée. Un
test vérifie que la fonction refuse de fabriquer un `x` ; deux autres qu'un témoin fabriqué qui ne
satisfait pas `R`, ou qui satisfait `post`, est refusé.

---

## 6. Budgets

L'ancien `_solve` faisait `max(deadline - now, 0.001)` : il démarrait un solveur même après
l'échéance, et `_run`/`_finish` acceptaient un SAT/UNSAT tardif. **Mesuré** : avec
`Budget(max_seconds=1e-9)`, l'ancien code renvoyait `accepted = True` — un certificat entièrement
hors budget.

Correction : une horloge unique `CompositionBudget`, démarrée **à l'entrée publique**, partagée par
les quatre obligations. Contrôle avant et après l'encodage, après création du solveur, pendant la
résolution (watchdog coopératif), puis après résolution, extraction du modèle, vérification du témoin
et nettoyage. Un résultat tardif devient `satisfiable=None` avec un détail `budget`, et
`check_composition` refuse alors de certifier. Un timeout n'est jamais confondu avec une précondition
insatisfiable : `timed_out` et le motif sont distincts.

`Obligation.seconds` va du début de l'obligation (encodage inclus) au retour, nettoyage compris : la
somme des quatre fait ~95 % du temps mural de l'appel.

Deux tests déterministes : encodage ralenti au-delà de l'échéance (`monkeypatch` sur
`encode_circuit`), et UNSAT rendu après l'échéance (solveur enveloppé qui dort puis répond).

---

## 7. Grammaire

`And(Var("x.0"), object())` construisait un nœud malformé et n'échouait qu'ensuite, dans `depth()`,
avec `AttributeError`. Chaque constructeur valide désormais ses sous-expressions, et `validate`
retraverse l'arbre avec une profondeur **bornée pendant** la traversée — un arbre de 4000 `NOT` lève
`ExprError` au lieu d'épuiser la pile. La limite de 24 est conservée.

---

## 8. Benchmark corrigé

L'ancien pilote comparait deux prédicats : le miter monolithique observait **les quatre** fils, la
composition **trois**. Il répondait donc « different » d'un côté et « accepted » de l'autre, et
appelait cela `ok`.

Les deux côtés utilisent maintenant `Contract(observed_outputs=(0, 1, 2))`.
Mesures (`RESULTS/composition_pilot.json`, 5 répétitions par run, Glucose 4.2) :

| | verdict | clauses |
|---|---|---:|
| miter monolithique (fils 0,1,2) | `equivalent` | 48 |
| composition (4 obligations) | `accepted` | 127 |

**Les deux verdicts concordent**, ce qui est la condition pour que la comparaison ait un sens.

**Sur le temps, je ne donne pas de ratio unique** : les deux côtés sont sous la milliseconde et le
ratio varie de **1,30× à 2,56×** sur quatre exécutions successives (médiane des médianes ≈ 1,7×). Un
chiffre précis serait du bruit présenté comme une mesure. Ce qui est stable, c'est le sens :
la composition est **plus chère**, et les tailles de CNF (127 contre 48 clauses) expliquent pourquoi
— quatre requêtes contre une, et les deux blocs encodés deux fois. L'ancien 2,78× est conservé sous
`historical_7e7b481`, marqué comme **non** comparable (prédicat différent, théorème plus faible).

Aucune tentative d'obtenir artificiellement un meilleur temps : le résultat reste défavorable à la
composition.

---

## 9. Ce que la correction ne donne pas

- **Pas de gain sur la correction globale.** L'exemple positif reste décidable par
  `check_sat_equivalence(..., Contract(observed_outputs=(0,1,2)))`. Le gain est un **lemme
  d'interface local réutilisable**, pas un nouveau decideur.
- **Pas de gain de performance.** 1,3× à 2,6× plus cher ici selon l'exécution, et les tailles de CNF
  (127 contre 48 clauses) sont, elles, stables.
- **Pas de preuve sur un circuit réel** : aucune donnée qant.
- Les préconditions ne portent que sur les entrées `x`, pas sur un état initial arbitraire : le
  modèle « ancilla empruntée » n'est pas exprimé.

---

## 10. Tests et reproduction

34 tests dans `tests/test_composition.py` : contre-exemples de l'audit, quatre obligations séparées,
exemple `Pre_B` non triviale et ses trois mutants, deux tests de budget déterministes, vérification
des témoins, fermeture de la grammaire. Suite complète : `3128 passed, 2 skipped`.

```
PYTHONPATH=src python -m pytest tests/test_composition.py -q
PYTHONPATH=src python research/symq-v2/pilot_composition.py
ruff check src/symq/sat tests/test_composition.py research/symq-v2/pilot_composition.py
```
