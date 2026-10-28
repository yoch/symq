# Décisions — adopter, reporter, abandonner

## Adopté

| axe | décision | preuve |
|---|---|---|
| **SAT** (`symq.sat`) | adopté comme moteur de décision optionnel | **17/17** tâches contre 15/17 pour le moteur symbolique, plus lent en médiane (1,39) mais seul à décider les deux cas difficiles, 0 désaccord, oracle exhaustif sur 40 paires |
| **Contrats** (`Contract`) | adopté | testé sur le vrai additionneur Cuccaro, domaine restreint, ancilla propre, permutation de fils |

## Reporté, avec condition de reprise

| axe | raison | condition |
|---|---|---|
| **Mark-copy natif** | le transfert ne coûte que 4 % du run (13 ms par collecte) ; le gain maximal est 4 % | un circuit où la collecte dépasse 20 % du run, ou un export de monômes qui explose alors que la table est petite |
| **Certificat UNSAT (DRAT/LRAT)** | le verdict UNSAT est aujourd'hui relatif à l'encodage ; un certificat indépendant serait plus fort | un usage où un tiers doit vérifier sans faire confiance au code |
| **Largeur > 64** | aucun circuit connecté intéressant au-delà de 64 fils n'a été identifié | un tel circuit, avec une question d'équivalence réelle |
| **HMR vers un corpus réel** | aucun programme public n'a montré que le critère de canal est *nécessaire* | un programme où O2 rejette un programme correct |

## Abandonné

| axe | raison |
|---|---|
| **Décomposition avec certificats** | aucune primitive originale identifiée ; les interfaces compactes ne se présentent pas là où l'expansion échoue ; voir `INTERFACE_PROOFS.md` |
| **Mark-copy comme optimisation prioritaire** | même raison que le report, mais l'abandon porte sur la priorité : ce n'est pas le prochain levier |

## Ce qui reste le comportement par défaut

Rien n'a changé dans le chemin par défaut : `identity`, moteur symbolique, cache lossless, pas de
collecte. La stratégie, la collecte et SAT sont des options explicites. C'est délibéré — la mission
demande de conserver les comportements historiques jusqu'à démonstration suffisante, et aucune des
trois options n'a été validée sur des architectures indépendantes.

## Le seul point où je ne suis pas d'accord avec l'énoncé de la mission

La mission demande de décider si le collecteur natif est « plus utile que le rebuild ». La réponse
mesurée est : **pas dans le rapport où la question se pose**. Le rebuild par monômes coûte 4 % d'un
run, donc un mark-copy ne peut pas changer la couverture ; ce qui change la couverture, c'est
d'activer la collecte, et c'est déjà fait. La question utile n'était donc pas « quel collecteur »
mais « collecte-t-on », et la réponse est oui, en option.
