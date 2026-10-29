# Reproduction des vérifications indépendantes

Tous les harnais de cet audit ne partagent aucune ligne avec le code audité. Ils sont exécutables.

## Préparation

Trois worktrees, chacun épinglé au SHA audité :

```bash
git fetch origin 38a137203205202367425b3f0317a7ae4faa2612 \
                 225f060897859b660e5e7afb3f1024e73777b051 \
                 f58f382276516f974306e51cd3f2d5c17398aad1 \
                 53da41e71dcdc3158fb80b9719572b5f5a44635b \
                 af8a874db66a8176e14419cda13cff13c6db0ef2

git worktree add --detach /tmp/audit/pr90 38a137203205202367425b3f0317a7ae4faa2612
git worktree add --detach /tmp/audit/pr94 53da41e71dcdc3158fb80b9719572b5f5a44635b
git worktree add --detach /tmp/audit/pr95 af8a874db66a8176e14419cda13cff13c6db0ef2
```

L'extension native doit être construite pour les mesures #95 :

```bash
cd /tmp/audit/pr95 && python tools/build_native.py
```

## Harnais

### `ref90.py` — référence CPTP dense (aucune dépendance)

Matrices denses sur `Fraction`, familles de Kraus appliquées puis sommées. Écrit depuis la liste des
portes, sans réutiliser l'oracle audité.

Piège méthodologique documenté dans le fichier : les deux opérateurs de reset **doivent rester séparés**.
Les fusionner en `|0⟩⟨0| + |0⟩⟨1|` produit une carte fausse ; c'est l'erreur que j'ai commise d'abord et
que la comparaison à main a révélée.

### `crosscheck90.py` — 24 cas contre la référence

```bash
cd /tmp/audit/pr90
PR90=/tmp/audit/pr90 PYTHONPATH=/tmp/audit/pr90/src:/tmp/audit/pr90 \
  python /path/to/raw/crosscheck90.py
```

Attendu : `24/24 cases agree with the independent reference`.

### `fuzz90.py` — 120 programmes aléatoires

```bash
cd /tmp/audit/pr90
PR90=/tmp/audit/pr90 PYTHONPATH=/tmp/audit/pr90/src:/tmp/audit/pr90 \
  python /path/to/raw/fuzz90.py
```

Attendu : `120 random programs x all matrix units x 2 trace modes: ALL AGREE`.

### `repro95.py` — reproduction du benchmark natif

```bash
PR95=/tmp/audit/pr95 AUDIT_PYTHON=python3 python raw/repro95.py
```

`AUDIT_PYTHON` doit pointer sur l'interpréteur où `python-sat` et l'extension native sont disponibles.

Sous-processus neufs, ordre des backends randomisé, 15 répétitions, RSS lu dans l'enfant, contrôle négatif
inclus. Écrit `pr95_repro.json` à côté du script.

### `interop9094.py` — interopérabilité #90/#94 (17 vérifications)

```bash
PR90=/tmp/audit/pr90 PYTHONPATH=/tmp/audit/pr90/src python raw/interop9094.py
```

Attendu : `17/17 interoperability checks pass`. Couvre le gadget canonique (canal + tracé), les 64
cohérences sommées sur l'issue, deux dettes, réutilisation de slot, correction après porte
non diagonale, et six mutants de correction.

**Note importante** : la référence doit être le circuit de **valeur** (`ccx(0,1,2)`), pas
`value_ops + reset`. `reset` décohère, donc il n'est canal-égal à aucun circuit unitaire. Choisir la
mauvaise référence est exactement l'erreur qui a produit mon faux finding P1.

Une version pytest de ces vérifications, rejouable en CI et **capable de détecter un oracle cassé**
(4 échecs sur une mutation de signe), est dans `tests/test_crossrepo_audit.py`.

### `parity95.py` — parité de grammaire native / Python (point 7 de #96)

```bash
PR95=/tmp/audit/pr95 PYTHONPATH=/tmp/audit/pr95/src:/tmp/audit/pr95 \
  python raw/parity95.py
```

Attendu : `GRAMMAR PARITY: HOLDS`, avec le nombre de rejets et de désaccords de verdict.

### `mutations.py` — points 4 et 5 de #96, mutations sémantiques

```bash
PR90=/tmp/audit/pr90 PR92=/tmp/audit/pr92 PR94=/tmp/audit/pr94 \
PYTHONPATH=/tmp/audit/pr90/src:/tmp/audit/pr92/src:/tmp/audit/pr94/src \
  python raw/mutations.py
```

Attendu : `17/17 mutations handled as expected`. Couvre : condition classique niée, `X` conditionnel
supprimé, canal identique / instrument différent, slot écrasé, `reset` vs `HMR`, retrait de la correction
#94, reçu périmé, préfixe/suffixe/embedding mutés, fil préservé non restauré, hash faux, flux candidat muté.

**Piège à éviter** : les circuits doivent être épinglés **une fois** depuis le transcript légitime, puis
tenus fixes pendant qu'on mute le transcript. Reconstruire les circuits à partir des étapes mutées rend la
mutation invisible — c'est l'erreur que ma première version commettait.

### Vérifications non scriptées

Les contrôles suivants ont été faits en session interactive et sont décrits dans les rapports ; ils sont
triviaux à rejouer :

- bijection combinadique exhaustive (`variables` 1..6, `degree` 0..4) ;
- certificats GF(2) vs énumération (5036 systèmes exhaustifs + 3000 aléatoires) ;
- balayage exhaustif du produit ANF (53 824 paires à `n=4, deg=2`) ;
- identité de factorisation de #95 vs oracle dense (312 unités) ;
- 60 paires de programmes : verdict natif vs oracle CPTP ;
- 150 programmes aléatoires pour la réparation #94 ;
- 200 transcripts chevauchants pour #92 ;
- profilage `cProfile` comparant les deux backends ;
- ASan/UBSan via `tools/sanitize_native.py`.

## Résultats bruts

- `pr95_repro.json` — mesures reproductibles du benchmark natif (15 répétitions par cellule).

Les autres résultats sont des compteurs déterministes (N accords sur N cas) reportés dans les rapports ;
ils sont reproduits à l'identique par les scripts ci-dessus.

## Ce qui n'a pas été reproduit

- Le benchmark de #93 (`benchmark.py`) : non exécuté faute de budget dans cette mission, et non revendiqué.
- Les temps de #92 et #94 : mesurés ponctuellement mais non soumis à un protocole apparié ; les seuls
  chiffres de performance que je cautionne sont ceux de #95, qui bénéficient d'un protocole complet.
- Aucun fragment réel de `yoch/qant` : le dépôt est privé, et aucun fixture privé n'est copié ici.
