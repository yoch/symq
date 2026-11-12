# Synthèse de phases bilinéaires après mesure

`symq.labs.bilinear_phase_fusion` est un laboratoire autonome, sans dépendance
native ni solveur SAT. Il synthétise exactement

```text
(-1) ** (c * sum_j dot(s_j, A * B_j))
```

où les produits sont calculés dans GF(2^m), en base polynomiale explicitement
spécifiée. Le contrôle `c` et les registres `A`, `B_j` sont quantiques, arbitraires
et éventuellement intriqués avec une référence extérieure. Les masques `s_j`
sont classiques, ordonnés mot par mot, bit de poids faible en premier.

## API expérimentale et théorèmes

```python
from symq.labs.bilinear_phase_fusion.compiler import compile_bank, digest
from symq.labs.bilinear_phase_fusion.checker import check_certificate

p = compile_bank(m=12, modulus=0x1053, bank=4)
certificate = {
    "schema": "bilinear-phase-branch-v1",
    "program_sha256": digest(p),
    "outcomes": [1, 0, 37, 4095],
}
result = check_certificate(p, certificate)
assert result["ccz"] == 12
```

Le compilateur émet un DAG classique XOR/AND et des CX/CCZ conditionnelles.
Il ne construit pas de table exponentielle d'issues. L'ordre des fils est
`c, A[0:m], B_0[0:m], ...`. Aucun qubit ni mesure n'est ajouté et tous les fils
sont restaurés. Pour un masque non nul, un bloc bilinéaire non dégénéré est
choisi et réduit par élimination de Gauss classique ; les autres blocs sont
absorbés dans ce bloc avant la phase, puis les transformations sont inversées.
Le masque entièrement nul n'exécute aucune porte.

`check_certificate` ne fait appel ni au compilateur ni à SAT. Il vérifie le hash,
la grammaire stricte, l'ordre de définition des sélecteurs, la restauration et
la matrice exacte des coefficients. Un succès concerne **une branche donnée,
sur toutes les entrées quantiques**. Il ne prouve pas que le registre mesuré
contenait le bon produit. Il n'importe aucun verdict positif stocké.

Une autre API vérifie cette préparation à partir d'un vrai `Circuit` :

```python
from symq.labs.bilinear_phase_fusion.preparation import emit_source, to_symq
from symq.labs.bilinear_phase_fusion.runtime import (
    preparation_document, check_source_certificate,
)

p = compile_bank(3, 11, 2)
source = to_symq(emit_source(3, 11, 2))
cert = {
    "schema": "bilinear-phase-erasure-branch-v1",
    "preparation_sha256": digest(preparation_document(source, p)),
    "program_sha256": digest(p),
    "outcomes": [1, 7],
}
assert check_source_certificate(source, p, cert)["theorem"] == "prepared_bilinear_erasure_branch"
```

Le contrat est fermé : le circuit entier est la frontière `[0, len(gates))` ;
les fils suivent l'ordre fixe ci-dessus, puis les garbage préparés à zéro.
L'ANF reconstruite depuis les portes X/CX/CCX/MCX doit prouver
`garbage_j=c*(A*B_j)` et restaurer chaque opérande vivant à sa version d'entrée.
Un drapeau `prepared=true`, une source sale, une porte de phase ou un mapping
arbitraire ne remplace pas cette obligation. Les deux hashes sont recalculés
au rejeu. Un changement de source doit recevoir sa propre vérification, même
si son hash déclaré a été actualisé.

Le théorème concerne l'effacement par HMR de ce producteur suivi de la correction
dans la branche choisie. Les `m*bank` résultats des HMR des garbage sont conservés
comme labels uniformes ; aucun résultat supplémentaire n'est créé. Les sorties
quantiques comprennent les registres vivants restaurés et les garbage remis à zéro.
Il n'établit pas une substitution dans une application ni une équivalence avec
un instrument comportant des mesures supplémentaires observées.

`runtime.correction_for_outcome(p, outcomes)` donne un véritable `PhaseProgram`
pour une branche vérifiée. Cette instanciation ne contient pas d'HMR et ne
représente pas le programme adaptatif complet : le `PhaseProgram` existant
n'accepte pas le DAG classique ni les CX conditionnelles. Ses API et ses
théorèmes conservent donc leurs valeurs de retour et leurs sémantiques.

## Correction, coûts et limites

Un masque non nul donne un rang bilinéaire `m`. Dans le fragment CX/CCZ, la
dérivée par rapport au contrôle a un rang polaire `2m` ; une CCZ contribue au
plus deux. Les `m` CCZ construites atteignent cette borne dans ce fragment.
Ce n'est pas une optimalité physique ou globale. Le vérificateur rend le rang
et le compte réel séparément ; un programme correct avec des portes redondantes
n'est pas déclaré optimal par son certificat.

La bonne référence pour une banque peut déjà être le cache partagé `U=c*A` :
il demande `m` AND, `m` qubits et `m` HMR de suppression, puis des phases
Clifford. La fusion supprime ce cache et ses mesures ; elle n'améliore pas son
nombre de primitives non-Clifford pour une branche non nulle. Les milliers de
nœuds classiques et les CNOT de préparation/restauration restent facturés dans
les rapports. Aucune promesse de vitesse, de pic mémoire d'application ou de
coût matériel n'en découle.

Les dimensions sont bornées à `2 <= m <= 16`, `1 <= bank <= 128`. Le constructeur
exige un polynôme irréductible. Le vérificateur d'identité d'une branche vérifie
les coefficients du polynôme déclaré ; il n'a pas besoin d'hériter du test
d'irréductibilité du compilateur. Les programmes classiques/quantiques et les
préparations ont des plafonds de taille ; les vérifications ont des délais
coopératifs et des limites de produits ANF. `Rejected` signifie refus ou échec
de l'obligation étroite ; `Inconclusive` signifie budget épuisé. Aucun n'est un
contre-exemple de canal. Ce code n'est pas formellement vérifié.

## Qualification reproductible

```bash
python -m pytest -q tests/test_bilinear_phase_*.py
python -m benchmarks.bilinear_phase_fusion --out /tmp/bilinear-new
```

La destination doit être nouvelle. Les résultats restent des artefacts locaux,
hors dépôt. Le rapport conserve le commit, les hashes de code, la commande,
Python, la machine, le RSS maximal du processus, trois temps de compilation,
la graine, les échecs et les budgets. Les temps sont de la provenance ; aucune
comparaison de performance n'est revendiquée.

La campagne couvre exhaustivement les issues des petits corps et les 4 096
masques GF4096 à un mot. Pour les banques GF4096 de 2, 4, 8 et 69 mots, elle
couvre respectivement 71, 75, 83 et 205 branches déterministes, **pas toutes les
issues**. Chaque branche réussie compare exactement toutes les entrées
quantiques. Il s'agit d'un corpus de développement construit ; aucun holdout
indépendant n'est revendiqué.

Les tests comprennent les colonnes Kraus exactes de petites instances, une
référence cohérente extérieure, les nouveaux adaptateurs exécutés dans SymQ,
des mutations de phase/restauration/garde/préparation/hash et des budgets
interrompus pendant la validation classique. La copie maintenue ici provient
des trois fichiers génériques fournis par l'utilisateur : SHA-256 d'origine
`compiler.py` = `40f5df5c06d3745dcfbd4ec3b03637b43e7ea41e57b9c9b607c4a4bcf4d44053`,
`checker.py` = `449e92908ea06238198375727b1dc31cdf93b1d6448abb1144570c356f41985c`,
`preparation.py` = `0ba8f2c0c4e9805f4bcf6f0b10e6097fb3b203c6a54080c2bca1b04e13ae2453`.
Le vérificateur et le compilateur sont maintenus séparément. Aucun tenseur,
fixture ou résultat privé n'est importé.
