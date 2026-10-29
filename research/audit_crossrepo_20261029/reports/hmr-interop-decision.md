# Rapport corrigé — décision définitive sur l'interopérabilité HMR

**Ce document corrige une conclusion erronée de mon audit précédent.** Il remplace le finding P1
« conventions HMR incompatibles entre #90 et #94 » publié dans le rapport transversal et sur les PR
#90 et #94.

Date : 29 octobre 2026. Base : `yoch/symq` `main`. PR #97 HEAD revalidé : `deb3397f127d430381f048293bd6e144051d6720`.

---

## 1. Décision : **cas A — l'interopérabilité fonctionne**

Le test de la mission est exécuté et **passe** :

```python
repaired = HybridProgram(3,1).ccx(0,1,3).cx(3,2).hmr(3,"b0").cz(0,1,condition="b0")
reference = HybridProgram(3,1).ccx(0,1,2)
assert same_channel(repaired, reference).equivalent   # True
```

| vérification | résultat |
|---|---|
| circuit corrigé == référence (canal complet, ancilla gardée) | **`True`** |
| circuit corrigé == référence (ancilla tracée) | **`True`** |
| circuit non corrigé == référence | **`False`** (comme attendu) |
| les 64 cohérences d'entrée, après somme sur l'issue observée | **0 écart** |
| `phase_semantics` : `{0b1011}` → `{}` | **dette annulée** |
| double correction | **`False`** (le signe ne s'applique qu'une fois) |

**Le finding P1 est retiré.** Il n'était pas fondé.

---

## 2. L'erreur d'analyse, précisément

L'algèbre que j'avais mal évaluée est élémentaire et la mission la donne correctement :

$$\text{signe de la branche Kraus } m : (-1)^{m\,g(x)}$$
$$\text{porte de correction conditionnelle} : (-1)^{m\,g(x)}$$
$$\text{produit} : (-1)^{2\,m\,g(x)} = 1$$

En ANF : `m·g(x) XOR m·g(x) = 0`. C'est exactement ce que `phase_semantics` rapporte.

**Pourquoi je m'étais trompé.** Ce n'était pas une question d'interprétation verbale : j'avais choisi
la **mauvaise référence**. J'ai comparé le circuit corrigé à

```
value_ops + reset(ancilla)
```

or `reset` est un canal **décohérent** : il ne peut pas être égal au circuit de valeur, qui est
unitaire. La mesure le confirme :

| programme | vs référence `ccx(0,1,2)` |
|---|---|
| corrigé | **`True`** |
| non corrigé | `False` |
| `value_ops + reset` | **`False`** ← ma référence était fausse |

Sur l'unité décisive `|000⟩⟨011|` :

| programme | matrice |
|---|---|
| référence | `{(0,7): 1}` |
| corrigé | `{(0,7): 1}` ✅ |
| non corrigé | `{}` (décohérencé) |
| `value+reset` | `{}` (décohérencé aussi) |

`value+reset` et le circuit non corrigé décohérencent tous deux, mais **différemment** : l'un tue la
cohérence par reset, l'autre par signe non compensé. Le fait qu'ils diffèrent entre eux (`False`) m'a
laissé croire que le corrigé devait aussi différer de la référence. C'était une erreur de raisonnement
par transitivité sur une relation qui n'est pas transitive.

**Le mécanisme réel**, vérifié branche par branche : sur `|000⟩⟨110|` (où `g = x0∧x1` vaut 0 d'un côté
et 1 de l'autre), le circuit corrigé donne `+1/2` dans **les deux** branches, donc la somme vaut 1 et
la cohérence survit. Sans la correction, les deux branches porteraient des signes opposés et la somme
serait nulle. La porte conditionnelle **aligne** les signes ; elle ne les réapplique pas.

---

## 3. Une contrainte réelle, qui n'est pas un défaut

Il existe une condition d'ordre véritable, et elle mérite d'être documentée car elle explique pourquoi
#94 recalcule la phase sur les **fonctions finales** plutôt que de supposer qu'elle commute :

**Une correction tardive n'est valide que si le monomial qu'elle utilise est encore celui qui a été
enregistré.** Si une porte de valeur modifie un des fils du monomial entre la mesure et la correction,
la correction porte sur une autre fonction et n'annule rien.

Vérifié :

| construction | résultat |
|---|---|
| porte non diagonale sur un fil **disjoint** du monomial, puis correction | **`True`** |
| porte qui **déplace** un fil du monomial, puis correction | **`False`** ← correct, la dette survit |

C'est un argument en faveur de #94, pas contre : le synthétiseur refuse ou recalcule au lieu de
supposer.

---

## 4. Couverture étendue exigée par la mission

Tous ces cas passent (**17/17** dans `raw/interop9094.py`) :

| cas | attente | résultat |
|---|---|---|
| gadget canonique, canal + tracé | égal | ✅ |
| non corrigé | différent | ✅ |
| `value+reset` n'est pas la référence | différent | ✅ |
| 64 cohérences sommées sur l'issue | 0 écart | ✅ |
| deux dettes annulées == identité | égal | ✅ |
| une seule dette sur deux corrigée | différent | ✅ |
| deux dettes autour d'une opération de valeur | égal | ✅ |
| même paire non corrigée | différent | ✅ |
| slot réutilisé, deux événements distincts | égal | ✅ |
| correction après porte non diagonale (fil disjoint) | égal | ✅ |
| correction après porte déplaçant un fil du monomial | **différent** | ✅ |
| correction sur les mauvais fils | différent | ✅ |
| condition inversée | différent | ✅ |
| double correction | différent | ✅ |
| ANF : HMR crée `m·(x0∧x1)` | `[0b1011]` | ✅ |
| ANF : `mcz_if` l'annule | `[]` | ✅ |

---

## 5. Ce qui reste vrai de mon analyse précédente

Je maintien une partie du constat, mais **reclassée** :

- Les deux composants emploient des **représentations** différentes (ANF symbolique d'un côté, branche
  de Kraus normalisée de l'autre). Ce n'est pas une incompatibilité, c'est une dualité : les deux
  décrivent le même opérateur.
- Il reste **utile** de documenter cette dualité, parce qu'un lecteur qui compare des objets internes
  sans normaliser en opérateurs physiques peut refaire mon erreur. C'est un point de **documentation**
  (P2), plus un point de correction (P1).
- La recommandation opérationnelle change de nature : non plus « trancher une convention », mais
  « comparer toujours via `same_channel` / le canal physique, jamais via les objets internes ».

---

## 6. Statut des autres findings après cette passe

| finding | statut | raison |
|---|---|---|
| **#90 / #94 : conventions incompatibles** | **RETIRÉ** | test d'interopérabilité réussi, 17/17 |
| **#93 : refus de degré « bug non documenté »** | **RECLASSÉ en limite volontaire** | l'issue #86 **exige** le rejet du débordement ; le README le documente ; mon balayage quantifie le coût (10,1 % sur `n≤5`), il ne révèle pas un défaut |
| **#95 : provenance du benchmark** | **RETIRÉ** | le README de #95 épingle déjà `7a75f827…`, le run CI et le fichier de résultats — vérifié sur le vrai HEAD |
| **#95 : garde 64 variables redondante** | **nouveau, P2** | en retirant la garde Python, le noyau C rejette quand même ; c'est de la défense en profondeur, pas un défaut |

---

## 7. Conséquence sur les commentaires publiés

Les commentaires déposés sur #90 et #94 contiennent le finding P1 désormais retiré. Ils ne seront pas
réécrits (ils font partie de l'historique de la revue), mais ce document et le rapport transversal
corrigé les **invalident explicitement**. Un commentaire de correction est déposé sur les deux PR.

Aucune fusion.
