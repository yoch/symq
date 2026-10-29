# Décomposition avec certificats — exploration, sans framework

## L'hypothèse

Deux circuits peuvent être équivalents alors que leurs fonctions intermédiaires explosent. La
question : peut-on découper la vérification en sous-problèmes dont les interfaces ont des relations
compactes, puis composer les preuves sans développer les fonctions globales ?

## Ce qui existe déjà, et qui borne l'ambition

| technique | ce qu'elle fait déjà |
|---|---|
| SAT sweeping / FRAIG (ABC) | trouve les équivalences locales entre nœuds et les réutilise |
| equivalence checking partitionné | découpe le miter en tranches indépendantes |
| relations de coupure (*cut points*) | résume un sous-circuit par sa fonction d'interface |
| réécriture arrière (RevSCA-2, Amulet-2) | annule des monômes avant expansion |
| vérification réversible (Wille 2009) | miter + SAT sur le fragment réversible |

Une contribution devrait donc être **plus** qu'une de ces techniques, ou une combinaison nouvelle
avec une garantie que les autres n'ont pas.

## Ce que cette mission a réellement produit sur cet axe

Un **résultat négatif argumenté** et un outil qui rend l'axe mesurable, pas un prototype :

1. **Le découpage naïf est déjà disponible et ne suffit pas.** `Circuit.connected_components`
   découpe un circuit en blocs indépendants, et le vérificateur les traite séparément. C'est le cas
   facile. Aucun des circuits difficiles mesurés dans cette mission n'est découpable ainsi : les
   additionneurs et les multiplicateurs sont connectés.

2. **Les interfaces compactes ne se présentent pas là où le besoin est.** Le cas d'usage idéal
   serait un bloc dont la relation d'interface est petite alors que les polynômes internes sont
   énormes. Sur l'additionneur Cuccaro, l'interface du bloc de retenue est *précisément* la fonction
   qui explose : il n'y a pas de compression gratuite à exploiter.

3. **Le contrat est le bon niveau, mais ce n'est pas une décomposition.** `Contract` (voir
   `CONTRACTS.md`) permet d'énoncer ce qu'on observe et ce qu'on exige ; il ne permet pas de
   composer deux preuves locales. C'est un préalable, pas la contribution.

## Ce qu'il faudrait pour que l'axe devienne scientifique

Une primitive qui satisfasse les cinq conditions suivantes, aucune n'étant acquise :

1. une représentation de relation d'interface **plus petite** que les fonctions qu'elle relie ;
2. une règle de composition dont la correction se prouve, pas se teste ;
3. un usage réel de la réversibilité (sans quoi le problème est le *equivalence checking* classique,
   résolu par SAT) ;
4. un traitement exact des ancillas, qui sont la seule chose vraiment propre au réversible ;
5. un circuit où la méthode termine et où l'expansion globale ne termine pas.

Le point 5 est le critère décisif, et il n'a pas été trouvé.

## Verdict

**`INCONCLUSIVE`, avec une pente négative.** Aucune primitive originale n'a émergé, et les trois
observations ci-dessus suggèrent que la décomposition générique est déjà couverte par la
littérature. La seule piste qui resterait spécifique — une obligation d'ancilla compositionnelle —
n'a pas d'exemple où elle paie.

Ne pas construire de framework. Si la piste est reprise, elle doit commencer par **un** circuit où
l'expansion échoue et où une interface compacte existe ; sans cet exemple, tout le reste est de la
spéculation.
