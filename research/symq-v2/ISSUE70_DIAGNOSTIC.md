# Diagnostic #70 — le prétraitement structurel a-t-il de la matière ?

**Décision : `STOP` pour l'élagage COI sous équivalence complète sur les familles mesurées. Le partage de préfixes reste non évalué en temps et n'est pas prioritaire ; passer à #71.**

Aucun code de prétraitement n'a été écrit. Ce document mesure la réduction qu'un prétraitement
*pourrait* obtenir, sur trois familles de paires, avec `diagnose_70.py` (analyseur non intrusif,
`RESULTS/issue70_diagnostic.json`).

## Résultats

| paire | portes G/D | préfixe commun | cône vivant G/D | élagable |
|---|---|---:|---:|---:|
| `synth/variant_shared_prefix` | 60 / 60 | 0,37 | 60 / 60 | **0,00** |
| `synth/variant_rewritten` | 60 / 86 | 0,00 | 60 / 86 | **0,00** |
| `synth/mutant_one_gate` | 60 / 61 | 0,18 | 60 / 61 | **0,00** |
| `synth/identical` | 60 / 60 | 1,00 | 60 / 60 | **0,00** |
| `indep/adder_8_self` | 49 / 49 | 1,00 | 49 / 49 | **0,00** |
| `indep/adder_12_self` | 73 / 73 | 1,00 | 73 / 73 | **0,00** |
| `indep/shared_prefix_then_diverge` | 45 / 45 | 0,89 | 45 / 45 | **0,00** |
| `contract/all_outputs` | 80 / 86 | 0,02 | 80 / 86 | **0,00** |
| `contract/one_output` | 80 / 86 | 0,02 | 76 / 82 | **0,05** |
| `contract/quarter_outputs` | 80 / 86 | 0,02 | 76 / 82 | **0,05** |

Le cône vivant est calculé en remontant depuis les sorties observées : une porte est vivante si sa
cible l'est, puis ses contrôles le deviennent. C'est exactement la règle qu'utiliserait un élagage
arrière.

## Ce que ces chiffres disent

**En équivalence complète, l'élagage ne retire rien — et c'est mathématique.** Quand toutes les
sorties sont observées, chaque fil est vivant par définition, donc chaque porte influence une sortie
et aucune ne peut être retirée. Les sept premières lignes le confirment à 0,00.

**Les paires identiques sont le pire alibi.** Elles ont un préfixe commun de 1,00 et un cône vivant
égal au circuit entier : un partage de préfixe y « gagne » tout, et il n'y a rien à prouver. Ce sont
aussi les instances les moins intéressantes qu'un vérificateur reçoit. Les utiliser comme preuve de
valeur d'un prétraitement serait une erreur de méthode, et le tableau montre pourquoi : la seule
ligne où le préfixe est élevé (`shared_prefix_then_diverge`, 0,89) a un cône vivant de 45/45, donc
un élagage nul et un partage de préfixe qui ne fait que dupliquer un résultat déjà trivial.

**Les contrats partiels ouvrent 5 %, pas 40 %.** Même en n'observant qu'une sortie sur douze, seules
4 portes sur 80 deviennent inutiles. La raison est structurelle : dans un circuit dense, presque
toutes les portes sont dans le cône de presque toutes les sorties. Un prétraitement ne peut pas
créer de la localité qui n'existe pas.

## Ce que cela implique pour #70

Les deux mécanismes ne sont **pas évalués par la même mesure** :

- **Élagage de cônes :** nul en équivalence complète par définition ; sur **ces dix paires** seulement, le maximum observé sous contrat partiel est 5 %. D'autres circuits peu couplés peuvent donner davantage.
- **Partage de préfixe :** il existe des préfixes importants (jusqu'à 89 % sur une paire non identique), mais le rapport ne mesure **ni les clauses réellement économisées ni le temps d'une implémentation partagée**. On ne peut donc pas conclure à un échec de performance ; la priorité est simplement faible en l'absence de paire difficile représentative.

Une réduction de **5 % des portes sur les cas observés** ne garantit ni 5 % de clauses en moins ni un temps total inchangé : la complexité SAT ne se déduit pas directement de la taille du CNF. Le corpus ne contient pas d'indice assez fort pour justifier une implémentation COI par défaut.

## Recommandation

**Passer à #71 (contrats relationnels).** C'est le seul des deux axes qui change ce qu'on peut
*exprimer*, et non seulement la taille de ce qu'on encode. Le diagnostic ci-dessus donne d'ailleurs
un argument positif pour #71 : les contrats partiels sont le seul endroit où la structure laisse du
jeu, et #71 est précisément le chantier qui exploite cette notion.

## Limites

Trois générateurs, dix paires, aucune mesure de temps. Le **0 %** COI en équivalence complète constitue une conséquence formelle de l'observation de tous les fils, et non un benchmark. Le **5 %** observé sur les contrats partiels est un résultat local et **pas une borne universelle**. Le partage des préfixes et les réécritures algébriques n'ont pas été mesurés : cette mission recommande de ne pas les développer sans cas d'usage et gain attendu documentés.
