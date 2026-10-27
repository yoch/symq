# Corpus public vérifié — MQT QCEC

**11 circuits source**, sélectionnés dans `munich-quantum-toolkit/qcec`, commit épinglé
`98d6784176bfeb6ef923d4d0220e8d486dc1982f`, sous
`test/circuits/original/` : cinq circuits de développement (`c2_181`,
`mod5adder_306`, `rd73_312`, `rd84_313`, `sym9_317`) et six circuits
réservés (`5xp1_194`, `alu1_198`, `dk27_225`, `cm150a_210`,
`pcler8_248`, `mlp4_245`).

Le fichier `qcec_packed.tsv` est une **normalisation sans perte des portes
acceptées**, et non une copie byte-for-byte de l'OpenQASM d'origine.
Chaque ligne porte `nom|nombre_de_qubits|git_blob_sha_original|séquence`.
Le vérificateur strict `tools/verify_qcec_sources.py` recalcule les onze
empreintes Git et compare exactement les séquences et registres en récupérant
les fichiers originaux. Le vérificateur est **optionnel et n'a pas été exécuté
dans ce conteneur dépourvu d'accès réseau** ; les fichiers source ont été
inspectés via le connecteur GitHub au SHA indiqué.

Grammaire : `a` = `X`, `b` = `CX`, `c` = `CCX`, `dK` = `MCX` avec `K`
contrôles. Les identifiants sont en base 36, séparés par un point et les portes
par une virgule. Les en-têtes, commentaires et espaces QASM sont omis, **pas les
portes** ; le parseur refuse toute instruction inattendue. Les registres ne
sont pas supposés propres : dans les expériences à domaine complet, **tous
les qubits sont des entrées libres**. Les instances restreintes fixent les
autres fils à zéro et sont étiquetées séparément.

Exemple : `d38.c.g.4` = `MCX` à trois contrôles (qubits 8, 12, 16) sur cible 4.

**Provenance et licence** : l'implémentation et les fichiers publics MQT QCEC
sont sous MIT ; voir `LICENSE_QCEC.txt` (copyright conservé). Les circuits
d'exemple sont pour la plupart historiquement plus anciens que 2026. **C'est
leur snapshot Git vérifié qui date de 2026**, pas nécessairement leur création.

Pour un nouvel échantillon, ne pas changer silencieusement les exemples de test ;
créer un fichier de corpus séparé et conserver SHA + mode de sélection.
