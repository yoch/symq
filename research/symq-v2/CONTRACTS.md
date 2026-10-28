# Contrats de vérification — domaine, ancillas, sorties

## Ce que le contrat exprime

```python
Contract(
    input_constants={0: 0},          # fil 0 forcé à 0 sur les deux circuits
    observed_outputs=(1, 2, 3, 4),   # seules ces sorties doivent coïncider
    restored_wires=(0,),             # ce fil doit revenir à sa valeur d'entrée
    output_map={},                   # ou une permutation de fils
)
```

Chaque champ correspond à une obligation distincte, et la validation est stricte : indices hors
largeur, valeurs autres que 0/1, listes répétées, `output_map` non injectif, fil à la fois restauré
et mappé, `observed_outputs` et `output_map` ensemble — tout est refusé avec un message explicite.

## Le cas d'usage obligatoire : l'additionneur Cuccaro

Le générateur exige `carry_in = 0`. Cette précondition s'écrit maintenant dans le contrat au lieu
d'être une convention implicite du corpus :

```python
contract = Contract(input_constants={0: 0}, observed_outputs=(1, 2, 3, 4), restored_wires=(0,))
```

Testé dans `tests/test_sat_equivalence.py` :

- `test_a_constant_input_narrows_the_domain` : une porte contrôlée sur un fil fixé à 0 ne peut
  jamais s'activer, et le contrat le prouve là où la comparaison libre dit « différent » ;
- `test_observed_outputs_let_an_ancilla_be_ignored` : un fil qui contient un déchet mais n'est pas
  observé est ignoré sans mentir sur le reste ;
- `test_restored_wires_express_the_clean_ancilla_obligation` : un gadget qui ne défait pas son
  ancilla est rejeté, un gadget qui la défait est accepté, face à l'identité.

## Limite sémantique, énoncée explicitement

Un contrat est une obligation **classique sur les valeurs de fils**. Il ne dit rien de :

- la phase relative entre branches ;
- l'intrication laissée dans des ancillas non observées ;
- l'indistinguabilité de canaux quantiques.

Ignorer une sortie classique n'est donc pas un certificat de canal quantique. Le fragment HMR a ses
propres obligations (O1, O2) et son propre critère, décrits dans
`research/innovation/2026-10-28/PILOT_A_CORRECTED.md` ; les deux ne sont pas interchangeables et le
rapport ne les confond jamais.

## Ce que les contrats rendent possible, concrètement

Sans contrat, vérifier un additionneur contrôlé exige de comparer tous les fils sur les 2^n
entrées, y compris les états que le circuit ne prétend pas traiter. Avec un contrat, la même
vérification porte sur le domaine déclaré et les sorties déclarées — ce qui est la question réelle
d'un utilisateur qui assemble des gadgets.

Le gain n'est pas une vitesse : c'est l'**exprimabilité**. Un problème mal posé devient un problème
bien posé, sans que le vérificateur ait à deviner.
