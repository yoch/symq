# SymQ V2 — bilan après intégration

**Intégré dans `main` le 28 octobre 2026 :** moteur SAT optionnel via
[#66](https://github.com/yoch/symq/pull/66) et stratégie expérimentale via
[#67](https://github.com/yoch/symq/pull/67). Aucun dispatch automatique
ni changement du backend symbolique ou de l'ordre `identity` par défaut.

## Composants disponibles

| Composant | État | Contrat |
|---|---|---|
| `symq.sat.check_sat_equivalence` | Intégré, option `.[sat]` | Équivalence booléenne exacte de circuits X/CX/CCX/MCX, ou `inconclusive` |
| `symq.sat.Contract` | Intégré | Constantes d'entrée, sorties observées, fils restaurés, permutation partielle, validation stricte |
| `symq.strategy.choose` | Intégré **à titre expérimental** | Recommandation seule, jamais de vérification ni de dispatch |
| Heuristiques d'ordre `identity`, `reversed`, `last_use` | Options explicites | L'ordre par défaut reste `identity` |
| Collecte ZDD native par reconstruction | Déjà disponible sur `main` | Opt-in et limites de durée/mémoire, voir [GC.md](GC.md) |
| Mark-copy natif, preuve par interfaces, HMR étendu | Non implémentés | Pistes de recherche, pas des promesses de production |

Le SAT est un **moteur de décision**, pas une représentation polynomiale et pas un
vérificateur quantique général. Un résultat `different` porte un témoin rejoué
par l'exécuteur concret ; `equivalent` est un verdict UNSAT du solveur pour
l'encodage et le contrat, sans certificat UNSAT externe. Les limites temporelles
sont **coopératives** : une phase Python/C déjà engagée peut dépasser l'échéance.

## Résultats : pilotes exploratoires, non benchmarks de publication

Le pilote SAT de 17 tâches rapporte 17/17 décidées avec Glucose 4.2 contre 15/17
pour le ZDD natif. Sur les 15 tâches communes, le ratio médian de durée SAT/ZDD
est 1,39 (SAT plus lent sur huit). Ce pilote précède les derniers correctifs
de temps et n'utilise pas des chemins de mesure identiques : ne pas attribuer
ses durées au SHA final intégré.

La campagne appariée de six tâches rapporte SAT 6/6, ZDD 4/6 et collecte 4/6,
sans désaccord, mais le résultat enregistré contient
`worktree_dirty=true` et un `git_head` antérieur au HEAD final.
Elle ne prouve donc pas les performances du code intégré.

La politique de choix sélectionne SAT sur toutes les 18 tâches de son pilote :
**EXPERIMENTAL — NO DEMONSTRATED SELECTOR GAIN**. Des tâches favorisent le
symbolique, sans que la règle les identifie. Aucun seuil n'a été calibré
sur de nouveaux jeux indépendants.

## Documentation et pistes ouvertes

- [SAT.md](SAT.md) et [SAT_REPORT.md](SAT_REPORT.md) : moteur, contrats et limites.
- [CONTRACTS.md](CONTRACTS.md) : domaine d'entrée, sorties et ancillas.
- [STRATEGY.md](STRATEGY.md) : heuristiques, regrets et preuves négatives.
- [GC.md](GC.md) : collecte mémoire ; [INTERFACE_PROOFS.md](INTERFACE_PROOFS.md) : décomposition différée.
- [DECISIONS.md](DECISIONS.md), [BASELINE.md](BASELINE.md) et [AUDIT_RESPONSE.md](AUDIT_RESPONSE.md).
- Issues [#44](https://github.com/yoch/symq/issues/44) et [#46](https://github.com/yoch/symq/issues/46) : campagnes comparatives propres, figées et indépendantes.

Les résultats JSON historiques sont conservés dans `RESULTS/` et l'histoire Git.
Ils ne doivent pas être rebaptisés comme une validation du dernier commit.

## Résultats négatifs archivés après intégration

- [Prototype XAG/SAT, pilote négatif](XAG.md) ([#69](https://github.com/yoch/symq/issues/69)) : pas de gain général établi contre l'encodeur SSA ; code expérimental **non intégré** dans `main`, conservé dans la PR #75.
- [Diagnostic de l'élagage COI et du partage de préfixes](ISSUE70_DIAGNOSTIC.md) ([#70](https://github.com/yoch/symq/issues/70)) : zéro porte élagable lorsque toutes les sorties sont observées ; observations partielles locales, partage de préfixes non chronométré.
- Les JSON originaux sont conservés dans `RESULTS/xag_pilot.json` et `RESULTS/issue70_diagnostic.json`. Le pilote identifie le code dans la branche expérimentale, non dans le `main` actuel.
