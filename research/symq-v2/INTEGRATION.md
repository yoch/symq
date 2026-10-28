# Intégration — dépendances, interfaces, et ce qui doit être fusionné dans quel ordre

## État des branches

| branche | contenu | dépend de |
|---|---|---|
| `cursor/sat-verification-f132` | `src/symq/sat/`, `tests/test_sat_equivalence.py`, `research/symq-v2/pilot_sat.py` | `main` (`ddfe7aa`) |
| `cursor/auto-strategy-f132` | `src/symq/strategy.py`, `tests/test_strategy.py`, `research/symq-v2/pilot_strategy.py`, la documentation, et **le merge local de la branche SAT** | `main` + SAT |

La branche stratégie contient la branche SAT fusionnée, parce que le pilote de stratégie a besoin de
mesurer SAT. La PR correspondante doit donc être lue comme « SAT + stratégie », ou être fusionnée
après la PR SAT.

## Interfaces, et pourquoi elles sont stables

**`symq.sat` ne touche pas `Algebra`.** C'est la décision d'architecture la plus importante : un
solveur ne peut pas exporter d'ANF sans énumérer ses modèles, donc il ne doit pas prétendre
implémenter cette interface. Conséquence : `make_algebra("sat", ...)` n'existe pas et n'existera
pas ; le point d'entrée est `check_sat_equivalence`.

**`symq.strategy` est une fonction pure.** `choose(circuit)` ne modifie rien et ne simule rien.
Elle retourne une décision et sa justification, que l'appelant applique ou ignore. Aucun couplage
avec le moteur.

**`collect_every` reste un contrat ponctuel.** La collecte invalide les identifiants de nœuds, donc
un manager qui l'active refuse une seconde simulation. C'est vérifié par un test
(`test_native_collection.py`), et c'est ce qui rend la combinaison « plusieurs racines » sûre : les
sorties d'un run avec collecte sont épinglées et comparées avant que quoi que ce soit d'autre ne
touche le manager.

## Ordre de fusion recommandé

1. **SAT** — n'ajoute qu'un paquet optionnel et des tests ; aucun comportement existant ne change.
2. **Stratégie** — ajoute un module pur et de la documentation, après SAT pour que son pilote soit
   reproductible.
3. Rien d'autre : les axes reportés ou abandonnés ne demandent pas de fusion.

## Tests croisés entre composants

Ce que la combinaison doit garantir, et qui est testé :

| interaction | garantie | test |
|---|---|---|
| collecte + comparaison de deux circuits | deux managers distincts, sorties épinglées, identifiants jamais réutilisés | `test_native_collection.py::test_the_returned_identifiers_belong_to_the_final_manager` |
| stratégie + ordre | l'ordre choisi est toujours une permutation valide | `test_strategy.py::test_the_selected_order_never_changes_the_verdict` |
| stratégie + SAT | quand SAT n'est pas installé, la politique retombe sur symbolique | `test_strategy.py::test_the_engine_rule_respects_availability` |
| contrats + témoin | un modèle SAT qui ne respecte pas le domaine lève une erreur interne | `test_sat_equivalence.py` (vérification du contrat dans le témoin) |

## Ce qui n'est pas testé en combinaison

Aucune campagne n'exécute **collecte + SAT + stratégie** sur le même circuit : les trois sont
mesurés séparément. C'est une limite du rapport, pas un oubli caché.
