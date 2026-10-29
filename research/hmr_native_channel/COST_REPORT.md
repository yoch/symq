# Coût réel du vérificateur de canal HMR — profil par phase et deux optimisations exactes

**29 octobre 2026, 17 h 30 (Asia/Jerusalem).** Base : `2ff32c72` + le correctif de #102 (`a9b5fef`).
Branche : `cursor/hmr-channel-cost-profile-f132`. Aucun changement de `src/symq/` hors la primitive
`rename` ajoutée au cœur C, qui n'est appelée par aucun chemin par défaut.

## 1. Où passe le temps

`check_full_channel` est un appel opaque. `profile.py` rejoue **le même algorithme** avec une horloge
par étape et vérifie que son verdict est identique à celui de `check_full_channel` ; le profil est
refusé si les deux divergent.

Familles publiées, backend natif, mesure unique représentative :

| cas | total | `outputs_x`+`outputs_y` | `kernels` | `phases` | produits ZDD |
|---|---:|---:|---:|---:|---:|
| affine 8 données / 130 HMR | 0,97 ms | 0,52 ms (54 %) | 0,10 ms | 0,00 ms | 701 |
| non linéaire 8 / 70 | **15,96 ms** | **13,33 ms (84 %)** | 0,11 ms | 0,00 ms | 1 261 |

Sur le cas non linéaire, `outputs_x` seul prend 97,1 ms en Python ZDD et 11,4 ms en natif ; les deux
moitiés coûtent presque la même chose (11,4 ms et 14,5 ms), et **les phases et les noyaux sont sous
1 % du total**. Le coût n'est donc pas dans le théorème de phase : il est dans la **construction de
`F(x)` et `F(y)`**.

Le compteur `zero_phase_final` / `zero_coefficients_final` confirme que `phi0` et tous les `g_j` sont
nuls à la fin sur ces familles. **Cela ne veut pas dire que leur calcul est gratuit** : ce module
mesure le travail intermédiaire, pas seulement le résultat final.

## 2. Optimisation A — réutilisation exacte de la moitié `y`

### L'observation

Pour un programme, les moitiés `x` et `y` appliquent **la même liste de portes** sur des variables
décalées. Mesuré à 8 données / 70 HMR : les sorties `x` ont 125, 117, 124, 118, 117, 126, 125, 109
nœuds, les sorties `y` exactement les mêmes tailles, avec des identifiants disjoints.

### La primitive

`NativeZDDManager.rename(node, map)` (`src/symq/backends/_zdd.c`) réécrit chaque `level` d'un nœud
par `map[level]` et ré-internne `(level, lo, hi)`. C'est une substitution syntaxique sur l'ANF, pas
une heuristique. La carte est `i -> i + n` pour les données et `i -> i - n` pour les ancillas : elle
est strictement monotone, donc le diagramme reste ordonné. Le coût est linéaire dans le diagramme
atteignable, mémoïsé par identifiant de nœud, et borné par le budget du manager.

### Vérification

Trois gardes, toutes exercées par les tests :

- **exactitude** : la moitié renommée est comparée nœud par nœud à la moitié recalculée
  (sorties, `phi0`, chaque `g_j`) ;
- **verdict** : le chemin renommé et `check_full_channel` doivent donner le même `equivalent`, la même
  raison et le même type de témoin, sur les 7 types de comparaison et 3 familles ;
- **robustesse** : identité, carte de mauvaise longueur, cible hors largeur, identifiant inconnu.

### Mesure, 49 paires en sous-processus isolés

| famille | données | HMR | recalcul | renommage | gain |
|---|---:|---:|---:|---:|---:|
| affine | 8 | 130 | 2,01 ms | 1,80 ms | 1,12× |
| affine | 16 | 500 | 7,69 ms | 6,85 ms | 1,12× |
| non linéaire | 6 | 10 | 0,45 ms | 0,42 ms | 1,06× |
| non linéaire | 8 | 30 | 2,77 ms | 1,77 ms | 1,56× |
| non linéaire | 8 | 70 | 16,96 ms | 8,48 ms | **2,00×** |
| non linéaire | 10 | 60 | 103,93 ms | 44,22 ms | **2,35×** |
| non linéaire | 12 | 25 | 1,27 ms | 1,04 ms | 1,22× |

Médiane **1,20×**, minimum 0,91×, maximum 2,39×, **0 désaccord de verdict**. Le minimum sous 1 est
conservé : sur un cas court, le renommage ajoute un coût fixe sans rien amortir.

**Plafond structurel** : la moitié `y` est gratuite, mais la moitié `x` de chaque programme reste
entière, et les deux programmes restent distincts. Le gain maximal est donc **2×** sur les étapes
symboliques, jamais davantage. Un cas à 2,35× dépasse 2× parce que le renommage évite aussi la
construction de nœuds intermédiaires que le recalcul repayait.

## 3. Optimisation B — décomposition en blocs, pour dépasser 32 bits de données

### La limite

`check_full_channel` a besoin de `2 * n_data` variables natives ; le masque est un `uint64_t`, donc
`n_data <= 32`. Mesuré : 32 décide, 33 lève `ResourceLimitExceeded("native pair variables", 64, 66)`.
Le backend Python `zdd` décide 33, 34, 36 et 40. Ce n'est donc **pas** une limite sémantique.

### La décomposition

Si la liste de portes se coupe en **composantes connexes disjointes de fils**, l'unitaire est un
produit tensoriel sur ces composantes, et le canal aussi. Deux programmes ont des canaux égaux si et
seulement si chaque composante coïncide. `blocks.py` :

1. calcule les composantes de chaque programme (union-find sur les portes) ;
2. prend la **partition jointe** des deux : le plus fin raffinement commun, qui est un facteur
   tensoriel pour les deux programmes à la fois ;
3. restreint chaque programme à chaque bloc et appelle `check_full_channel` dessus.

Une opération qui traverserait la frontière d'un bloc fait **échouer** `restrict` au lieu d'être
renumérotée à l'aveugle. Un bloc encore trop large lève `ResourceLimitExceeded` : il n'est jamais
sauté en silence, donc une égalité partielle ne peut pas être rapportée comme une égalité.

### Résultat

| données | natif monolithique | décomposition native | Python monolithique | verdict |
|---:|---|---|---|---|
| 36 | `ResourceLimitExceeded` | **équivalent, 3,0 ms** | équivalent | identique |
| 40 | `ResourceLimitExceeded` | **équivalent, 3,5 ms** | équivalent | identique |

Sur 12 programmes larges aléatoires (34, 36, 40 données ; 4, 8, 12 HMR), **0 désaccord** avec le
monolithe Python. Un programme large dont la dernière réparation est retirée est détecté
(`equivalent=False`), et trois mutants par suppression d'opération concordent aussi.

**Quand elle ne s'applique pas** : si une composante dépasse 32 fils de données, la décomposition ne
gagne rien. C'était le cas de la famille 36/20, dont la composante la plus large fait 31 fils de
données. Le gain dépend donc de la structure du circuit, et `width_study.py` le rapporte pour chaque
programme au lieu de le supposer.

### La troisième voie, non implémentée

Un masque natif sur deux mots (`uint64_t[2]`) lèverait la limite pour **tous** les circuits, pas
seulement ceux qui se décomposent. C'est un changement de représentation dans le cœur C : clé de
hachage des nœuds, `min_masks`, conversion `from_terms`/`anf` vers les entiers Python. Le théorème ne
change pas. Coût estimé depuis le programme réel à 36 données : 72 variables, 2 mots.

## 4. Recommandations

1. **Ne pas promouvoir la décomposition comme remplacement** : c'est un pilote qui ne s'applique
   qu'aux circuits à composantes étroites, et il faut vérifier la partition à chaque paire.
2. **Le renommage est le seul gain général** : exact, vérifié nœud par nœud, et il divise par deux le
   travail symbolique sans changer le théorème. C'est le candidat naturel à une intégration dans
   `check_full_channel` lui-même, sous un drapeau, avec la contre-vérification déjà écrite ici.
3. **Pour dépasser 32 bits partout**, il faut le masque double-mot. Aucune autre voie exacte n'a été
   trouvée qui préserve toutes les cohérences.
4. **Aucun résultat de production** : tout reste sous `research/`, aucun défaut n'est modifié.

## 5. Reproductibilité

```bash
python tools/build_native.py
python -m research.hmr_native_channel.profile --backend zdd-native
python -m research.hmr_native_channel.rename_bench --repetitions 7 \
    --out research/hmr_native_channel/RESULTS/rename-20261029.json
python -m research.hmr_native_channel.width_study
python -m pytest -q tests/test_hmr_channel_cost.py
```

Résultats bruts : `RESULTS/rename-20261029.json`, `RESULTS/width-20261029.json`.
