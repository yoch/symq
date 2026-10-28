# Rapport SAT et contrats — SymQ V2

Périmètre : `src/symq/sat/`, `Contract`, les tests associés et le pilote de couverture. La
stratégie automatique et les documents de synthèse V2 sont sur leur propre branche.

## 1. Ce qui est implémenté

**Moteur de décision** (`symq.sat`). Encodeur Tseitin, miter, trois issues distinctes, témoin
rejoué par `Circuit.run`. Ce n'est **pas** un `Algebra` : il ne promet aucune exportation d'ANF.

**Contrats** (`Contract`) : entrées constantes, sorties observées, fils restaurés, permutation de
fils, validation stricte, exercés sur le vrai additionneur Cuccaro.

## 2. Ce que SAT apporte, mesuré

17 tâches, budget 30 s réels / 4 M nœuds, construction du CNF incluse dans la colonne SAT :

| moteur | décidées | temps total |
|---|---:|---:|
| ZDD natif | 15/17 | 6,34 s |
| ZDD + collecte | 13/17 | 5,59 s |
| **SAT** | **16/17** | **0,45 s** |

- **Couverture** : SAT décide `rand14x160_diff`, que les deux moteurs symboliques échouent au
  budget. C'est le gain réel.
- **Exactitude** : aucun désaccord entre moteurs sur les tâches décidées par plusieurs.
- **Vitesse** : médiane du ratio SAT/ZDD de **0,69** sur les tâches communes, mais SAT est **plus
  lent sur 7 des 15**, parfois de plus de 20× : sous la milliseconde son coût d'encodage domine.

## 3. Trois défauts trouvés par l'audit et corrigés

**Validation de l'IR.** `build_miter` et `encode_circuit` ne validaient pas les circuits, donc une
porte inconnue était encodée comme un flip et un circuit invalide pouvait être certifié. Les deux
valident maintenant avant d'émettre une clause ; la sonde de l'audit est devenue un test.

**Le budget n'était pas une limite de temps.** `conf_budget` compte des conflits. Pire : le premier
correctif utilisait `Cadical195.interrupt()`, qui lève `NotImplementedError` — le watchdog ne
pouvait donc rien interrompre, et les « 0,03 s » venaient du plafond de conflits.

Le moteur choisit maintenant un solveur **interruptible** (Glucose 4.2 en pratique ; CaDiCaL et
Kissat sont refusés), et `tests/test_sat_timeout.py` prouve la distinction : sur une instance
difficile, une interruption à 1 s rend la main en moins de 5 s avec `None`, ce qu'un plafond de
conflits ne produirait pas au même instant.

**Les tests ne tournaient pas en CI.** `python-sat` est dans les extras `test`, `dev` et `sat` ;
les deux jobs vérifient explicitement `symq.sat.available()` ; `test_sat_availability.py` échoue au
lieu de sauter quand le solveur manque.

## 4. Ce que SAT ne fait pas

Pas d'ANF, donc pas de témoin de degré minimal ni d'inspection polynomiale. Pas de certificat UNSAT
vérifiable indépendamment (DRAT/LRAT serait la suite). Optionnel : sans `python-sat`, `available()`
est faux et l'appel lève.

## 5. Verdicts

**Moteur : `MAJOR_COVERAGE_GAIN`** — un circuit non décidable au budget l'est maintenant, vérifié
par oracle exhaustif.
**Recherche : `KNOWN_TECHNIQUE_ONLY`** — l'encodage Tseitin et le miter sont des techniques connues.
