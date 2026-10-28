# Composition relationnelle — pilote #71

**Décision : `EXPERIMENTAL`, avec `STOP` sur l'idée que la composition réduit le coût.**

Le pilote est correct, testé et il démontre exactement ce que l'issue demandait de démontrer ou de
réfuter : une interface **relationnelle** est plus expressive qu'une égalité fil à fil, elle
fonctionne, et sur l'exemple mesuré elle **coûte 2,78× plus cher** que le miter monolithique.

## Ce qui est implémenté

`src/symq/sat/assumptions.py` — IR booléen fermé et validé : `Const`, `Var`, `Not`, `Xor`, `And`,
`Eq`, profondeur bornée à 24, variables déclarées obligatoires, rejet de tout objet hors grammaire
(y compris les callables Python, explicitement interdits par l'issue). Encodage Tseitin exact, chaque
connecteur étant une biconditionnelle.

`src/symq/sat/composition.py` — la règle de composition, en quatre requêtes SAT :

| nom | requête | attendu |
|---|---|---|
| `domain` | `P(x)` | **SAT** — sinon tout le reste est vacueux |
| `prefix` | `P(x) ∧ ¬R(A(x), A'(x))` | UNSAT |
| `interface` | `R(u,v) ∧ ¬Pre_B(u)` | UNSAT |
| `composition` | `R(u,v) ∧ Pre_B(u) ∧ ¬post(B(u), B'(u'))` | UNSAT |

## L'exemple

Largeur 4, deux blocs :

- `A` : `ccx(0,1,2)` — le produit `x0 AND x1` arrive sur `x2` ;
- `A'` : la même chose **plus** `x(3)`, qui salit une scratch que le suffixe ne lit jamais ;
- `B` : `cx(2,0)` — lit `x2`, écrit `x0` ;
- `R(u,v) := u.x2 = v.x2`, sur 2 variables et de profondeur 2.

Le point important : `A` et `A'` laissent des états de coupe **différents** (`x3` diffère), donc
aucune égalité fil à fil ne peut les relier — et c'est ce que le test
`test_dropping_the_correlation_makes_a_false_composition_pass` démontre : exiger l'égalité sur
`x3` fait rejeter une composition correcte.

## Résultats mesurés (`RESULTS/composition_pilot.json`)

| | temps médian | clauses | variables |
|---|---:|---:|---:|
| miter monolithique | **0,16 ms** | 52 | 20 |
| composition (4 requêtes) | **0,45 ms** | 112 | — |
| ratio | **2,78×** | 2,2× | — |

Détail par obligation : `domain` 2 clauses, `prefix` 36, `interface` 9, `composition` 65.

**La composition coûte plus cher, et c'est structurel** : elle paie quatre requêtes là où le miter
en fait une, et la somme des clauses dépasse celle du miter (112 contre 52) parce que les deux
blocs sont encodés une fois pour le préfixe et une fois pour le circuit complet. Sur un circuit de
quatre portes, aucun découpage ne peut amortir ce surcoût.

## Ce que la composition apporte quand même — et qui n'est pas du temps

Trois choses que le miter monolithique ne peut pas exprimer :

1. **Une relation sur l'état intermédiaire.** Le miter compare des sorties finales ; il ne peut pas
   dire « les deux préfixes doivent coïncider sur `x2` mais peuvent différer sur `x3` ». C'est le
   seul mécanisme testé ici qui accepte une paire de préfixes structurellement différents.
2. **Une obligation locale réutilisable.** `R ⇒ Pre_B` est vérifiée une fois et vaut pour tout
   suffixe qui suppose `Pre_B`, sans ré-encoder les préfixes.
3. **Un diagnostic localisé.** Quand la composition échoue, l'obligation qui échoue nomme le bloc
   fautif ; le miter monolithique ne dit que « les sorties diffèrent ».

Aucune de ces trois propriétés n'est un gain de temps sur l'exemple mesuré.

## La règle est-elle saine ?

Oui, et l'argument tient en quatre lignes. Pour tout `x` satisfaisant `P` : (1) donne `R(u,u')` ;
(2) donne `Pre_B(u)` ; (3) quantifie sur toutes les paires `(u,u')` satisfaisant `R ∧ Pre_B` et
impose `post` à leurs images. Comme `R` est assertée **conjointement** sur `u` et `u'` dans une
seule requête, aucune corrélation entre les deux états de coupe ne peut être oubliée : une
composition qui laisserait tomber une corrélation satisferait (1) tout en échouant (3). C'est
exactement ce que vérifie le test adversarial, où `R = TRUE` fait passer le préfixe fautif et le
fait rejeter par `composition`.

## Contre-exemples couverts

- préfixe qui corrompt le fil lu → rejeté par `prefix`, témoin rejoué ;
- suffixe qui ajoute un `x(3)` parasite → rejeté par `composition`, et la composition rejetée est
  effectivement fausse par exécution exhaustive ;
- précondition contradictoire `x0 ∧ ¬x0` → **refusée** avec `domain` UNSAT et aucune implication
  tentée, ce qui interdit le certificat vacueux ;
- égalité fil à fil → rejette une composition correcte (contrôle négatif de l'expressivité).

## Limites

- Un seul exemple, quatre portes. Aucune conclusion sur des circuits réels.
- `Pre_B` est `TRUE` dans l'exemple : l'obligation `interface` est donc trivialement satisfaite. Un
  exemple où `Pre_B` est une contrainte réelle reste à construire.
- Les préconditions ne portent que sur les entrées `x`, pas sur un état initial arbitraire : le
  modèle « ancilla empruntée » n'est pas exprimé ici.
- **Aucune donnée qant** : le dépôt est privé et l'issue interdit d'en copier les circuits. Aucun
  bénéfice pratique sur qant n'est donc démontré, et ce document ne le prétend pas.

## Décision

**`KEEP`** pour l'IR d'assumptions et la règle de composition : corrects, testés, et ils rendent
exprimable une obligation que le miter ne peut pas formuler.

**`STOP`** sur l'argument de coût : sur l'exemple mesuré, composer coûte 2,78× le miter, et rien
dans les données ne suggère une inversion sur des circuits plus gros — la composition encode
toujours les blocs une fois de plus.

**Prochaine étape utile, si elle est financée :** un exemple à `Pre_B` non trivial et à interface
beaucoup plus petite que les blocs, pour tester si la réutilisation de l'obligation locale peut
amortir le surcoût. À défaut, ne pas étendre #71 en framework.
