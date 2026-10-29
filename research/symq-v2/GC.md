# Collecteur ZDD — pourquoi le mark-copy natif n'a pas été construit

## La décision, et le chiffre qui la fonde

La mission demande un collecteur *mark-copy* qui copie le sous-DAG vivant sans passer par les
monômes. Le raisonnement est solide : l'export des monômes peut être gigantesque même quand le ZDD
est compact.

**Mesure du coût réel du transfert actuel**, 13 fils × 170 portes, collecte par porte à un seuil de
400 000 nœuds (le protocole exact du pilote C) :

```
total 7,85 s   GC 0,33 s (4 %)   collectes 25   par collecte 13 ms
```

Le transfert par monômes explicites — la méthode que le mark-copy devait remplacer — coûte **4 % du
temps total**, soit 13 ms par collecte. Un mark-copy parfaitement gratuit ferait donc gagner au
mieux 4 % sur ce circuit, et il faut encore lui payer sa propre écriture, ses tests, son risque
d'invalidation d'identifiants.

Ce chiffre contredit l'intuition de départ, et c'est pour cela qu'il fallait le mesurer : le
transfert est cher *en absolu* sur certains circuits (le cas 14×200 montre 0,27 s de rebuild pour
une simulation de 55 s), mais il reste toujours une petite fraction du run, parce qu'il ne se
déclenche que quelques dizaines de fois.

## Ce qui a été fait à la place

Le collecteur existant a été rendu *utilisable*, ce qui manquait davantage :

1. **Intégré au moteur** (`NativeZDDAlgebra(collect_every=n)`), avec un découpage adaptatif des
   tranches de portes. Avant, c'était un prototype hors du moteur ; le gain de couverture n'était
   pas accessible depuis `check_equivalence`.
2. **Contrat de propriété explicite** : la collecte exige un manager neuf et un seul run, sinon
   les identifiants exposés à Python seraient invalidés silencieusement. Le moteur refuse plutôt
   que de corrompre.
3. **Vérifié contre un oracle de table de vérité** sur 16 384 entrées, dans un sous-processus par
   bras, avec RSS par bras.

Résultats de cette intégration, sur 14 fils × 200 portes, graine 7 :

| configuration | statut | temps de calcul | pic RSS |
|---|---|---:|---:|
| sans collecte | **budget dépassé** | 65 s | 6 920 Mio |
| `collect_every=400_000` | **termine** | 44 s | **931 Mio** |

Sur quatre circuits (deux largeurs, deux graines), la mémoire s'améliore de **6 à 14×** ; le temps
s'améliore sur trois et **régresse de 1,44× sur un**. La revendication est donc une revendication
de couverture et de mémoire, pas de vitesse.

## Ce qu'un mark-copy apporterait encore, en théorie

- Il supprimerait le coût d'export des monômes, donc les 4 % ci-dessus.
- Il éviterait le cas où l'export lui-même explose : un polynôme à 10⁸ monômes dont le ZDD est
  compact. **Ce cas n'a pas été rencontré** dans les circuits mesurés. C'est la seule raison
  sérieuse de l'écrire un jour, et elle demande un exemple, pas un argument.

## Condition de reprise

Écrire le mark-copy si, et seulement si, un circuit réel montre un temps de collecte qui dépasse
~20 % du run, ou un export de monômes qui dépasse le budget alors que la table de nœuds est petite.
Aucun des deux n'est observé aujourd'hui.

**Correction après audit (28 octobre).** Le raisonnement « 4 % donc gain maximal 4 % » ne vaut que
pour les circuits mesurés, où l'export reste bon marché. Un ZDD compact peut représenter un
polynôme à un nombre exponentiel de monômes : l'export devient alors impossible alors qu'une copie
directe du DAG serait triviale. Le 4 % mesure le coût *observé*, il ne borne pas le coût *possible*.
La décision est donc un **report**, pas un abandon, et la condition de reprise inclut explicitement
un test synthétique adversarial : une famille dont le ZDD est compact et l'ANF gigantesque. Tant que
ce cas n'existe pas dans nos circuits, la priorité reste ailleurs ; s'il apparaît, le mark-copy
devient la seule voie.

### Le cas adversarial, mesuré

La famille `f = AND_i (x_2i XOR x_2i+1)` a un ZDD de `2k` nœuds environ et `2^k` monômes :

| k | fils | nœuds du ZDD | monômes | coût de l'export |
|---:|---:|---:|---:|---:|
| 16 | 32 | 288 | 65 536 | 0,006 s |
| 20 | 40 | 460 | 1 048 576 | 0,13 s |
| 24 | 48 | 648 | 16 777 216 | 2,41 s |
| 26 | 52 | **754** | **67 108 864** | **11,13 s** |

À `k = 26`, le diagramme tient en 754 nœuds — qu'une copie de DAG recopierait en microsecondes —
tandis que passer par les monômes coûte 11 s et 67 millions d'entrées. Le rapport entre les deux
croît exponentiellement en `k` : à `k = 32` l'export demanderait des heures et des centaines de Gio.

C'est la démonstration que la borne « 4 % » était locale. Un collecteur qui reconstruit par
monômes **ne peut pas** collecter cette famille ; un mark-copy le pourrait. La priorité reste
ailleurs parce qu'aucun circuit de nos corpus n'a cette forme, mais la limitation est maintenant
chiffrée et non plus supposée.

## Ce qui reste vrai et doit être dit

La décision repose sur un circuit et une famille de seuils. Un circuit où les racines vivantes
porteraient une part importante du DAG (le cas « le GC ne peut pas aider ») rendrait le transfert
proportionnellement plus cher, et la conclusion pourrait s'inverser. Le pilote C6/C7 n'en contient
pas ; le dire fait partie du résultat.
