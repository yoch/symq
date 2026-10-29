# Archive d'audit externe — statut : `ARCHIVE_NOT_AVAILABLE`

**Recherche effectuée le 29 octobre 2026, avant toute autre opération de cette mission.**

## Ce qui était attendu

La mission annonçait une archive privée (nom volontairement expurgé dans cette version publique), représentée ici par `external_reference_bundle.zip` : 65 fichiers, un
`README_FOR_AGENT.md`, un `MANIFEST.json`, un `SHA256SUMS`, et un commit source épinglé
`040baca30fe2bc8f6b8258e8be6a6c76a613e8c4`.

## Recherche réellement exécutée

| recherche | portée | résultat |
|---|---|---|
| `find / -iname "*[motif expurgé]*"` | tout le système de fichiers, une seule partition | **0 résultat** |
| recherche par motifs d’archive et de dépôt (motifs privés expurgés) | idem | 3 fichiers, aucun n'est l'archive (voir ci-dessous) |
| `find / -name "README_FOR_AGENT*" -o -name "SHA256SUMS*" -o -name "MANIFEST.json"` | tout le système | aucun `README_FOR_AGENT` ; les `SHA256SUMS`/`MANIFEST.json` trouvés appartiennent à des campagnes SymQ antérieures et à `qcec`, pas à un bundle d'audit |
| `find / -name "*.zip" -o -name "*.tar.gz" -o -name "*.7z"` filtré | tout le système | uniquement des archives de polices, de toolchains Go et des logs `gh` |
| recherche textuelle du nom historique (expurgé) | tout le système | **0 résultat** |
| points de montage | `mount` | un seul disque (`/dev/vdc`), plus le store d'agent `cursor-agent-store` |
| `/cursor/stores/user`, `/cursor/stores/self`, `/cursor/stores/bc-af7ccddf-…` | stores d'agent montés | artefacts de sessions précédentes seulement, aucun bundle |
| `/mnt`, `/uploads`, `/data`, `/workspace/uploads` | répertoires d'upload usuels | vides ou inexistants |
| MCP / ressources dynamiques | `GetDynamicTools` | aucune ressource de fichier exposée |

**Conclusion : `ARCHIVE_NOT_AVAILABLE`.** Chemin attendu : un fichier nommé
une archive privée, déposé dans le répertoire d'uploads de la session ou monté
dans l'espace de travail. Aucun fichier de ce nom, ni aucun répertoire contenant un
`README_FOR_AGENT.md`, n'existe dans cet environnement.

## Ce que cela **n**'autorise pas

Conformément à la mission : je ne remplace pas l'absence par une supposition. Les éléments suivants
restent **non vérifiés** et ne reçoivent aucun statut de réussite :

- les contrats de substitution temporelle historiques et leurs préconditions ;
- les preuves HMR/GF12 de la référence externe ;
- les implémentations de bitsets / ANF combinadiques / domaines légaux historiques ;
- les prototypes de correction de dette de phase de la référence ;
- les tests indépendants et adversariaux de la référence ;
- les rapports historiques de qualification et le commit `040baca3…`.

## Ce que cela **n**'empêche pas — et qui a donc été fait

L'absence d'archive ne bloque **aucune** des conclusions de cette passe, parce que la question
principale — l'interopérabilité #90/#94 — se tranche entièrement sur du code public :

- `research/hybrid_channel/oracle.py` (#90) et `src/symq/phase.py` (`phase_semantics`) sont dans des
  branches publiques de SymQ ;
- le test d'interopérabilité est exécutable sans aucune ressource privée ;
- les 17 vérifications de `raw/interop9094.py` tournent sur le seul code public.

**La décision définitive sur l'interopérabilité HMR est donc établie sans l'archive.**

## Matrice de provenance des références externes

Statut de chaque obligation que la mission voulait confronter aux ressources de l'archive. Aucune
ligne n'est marquée « reproduite » sans exécution réelle.

| Source | Obligation examinée | Reproduite ? | Tests | Limites |
|---|---|---|---|---|
| Archive `external_reference_bundle.zip` | contrat de substitution temporelle vs #92 | **non — archive absente** | aucun | `ARCHIVE_NOT_AVAILABLE` |
| idem | preuves HMR/GF12 vs sémantique #90/#94 | **non — archive absente** | aucun | idem |
| idem | bitsets/ANF/domaines légaux vs #93 | **non — archive absente** | aucun | idem |
| idem | prototypes de dette de phase vs #94 | **non — archive absente** | aucun | idem |
| idem | tests adversariaux de la référence | **non — archive absente** | aucun | idem |
| idem | rapport de qualification historique, commit `040baca3…` | **non — archive absente** | aucun | idem |
| `yoch/symq` PR #90 @ `38a1372` | canal CPTP, instruments | **oui** | `tests/test_crossrepo_audit.py`, `raw/ref90.py`, `raw/interop9094.py` | largeur ≤ 6, exponentiel |
| `yoch/symq` PR #92 @ `225f060` | preuve de transcript, mutations | **oui** | `tests/test_crossrepo_audit.py`, `raw/mutations.py` | permutations classiques uniquement |
| `yoch/symq` PR #93 @ `f58f382` | bijection colex, certificats GF(2), ANF | **oui** | `tests/test_crossrepo_audit.py`, balayage 9,6 M | limite de degré volontaire |
| `yoch/symq` PR #94 @ `53da41e` | réparation de dette, interop #90 | **oui** | `raw/interop9094.py`, `raw/mutations.py` | modèle de phase conditionné |
| `yoch/symq` PR #95 @ `af8a874` | canal natif, parité, limite 64 | **oui** | `tests/test_crossrepo_audit.py`, `raw/repro95.py`, `raw/parity95.py` | familles synthétiques |
| `yoch/symq` PR #96 @ `7a6f71a` | checklist, liens, provenance | **oui** | `reports/pr96-checklist-verification.md` | document, pas de code |

## Reprise si l'archive est fournie

Protocole prévu, inchangé :

1. `unzip -l` avant extraction, pour lister les membres sans écrire ;
2. lecture de `README_FOR_AGENT.md` ;
3. vérification de `MANIFEST.json` et `SHA256SUMS` contre les 65 fichiers annoncés ;
4. contrôle que le commit épinglé est bien `040baca30fe2bc8f6b8258e8be6a6c76a613e8c4` ;
5. extraction dans un répertoire **hors du dépôt** (`/tmp/external_bundle`), jamais dans `/workspace` ;
6. exécution des tests autonomes, en notant leurs dépendances réelles ;
7. rédaction de la matrice de provenance dans un **rapport privé**, avec hashes seulement.

Aucun fichier de l'archive ne sera copié dans SymQ public, et aucune dépendance runtime ne sera créée.
