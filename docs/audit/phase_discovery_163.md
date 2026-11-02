# Mission d'audit externe — SymQ #163, avant intégration

Tu es l'agent d'audit indépendant et de préparation à l'intégration du dépôt `yoch/symq`.
La mission porte sur **la totalité de la PR #163**, pas seulement son dernier commit : découverte à dictionnaire fixe, enrichissement adaptatif, séparateurs, initialisation par les sources et nouveaux certificats factorisés. L'issue d'audit et le commentaire de remise de mission donnent le HEAD final à revalider.

## Objectif, autorisations et méthode

Produis un verdict argumenté sur la correction mathématique, les frontières de confiance, les ressources, la reproductibilité et l'intégrabilité en `symq.labs`. Corrige les défauts reproduits dans la branche existante, avec régressions. Ne te contente pas de relancer les campagnes de l'auteur.

**Aucune autorisation de fusion.** Ne modifie pas `main`, ne fais pas de force-push, n'active aucun moteur par défaut, ne promeus aucun module dans l'API maintenue et n'ouvre pas une PR d'assemblage redondante. #163 cible déjà `main` et contient ses propres dépendances intégrées. L'audit précédent #164 et l'assemblage #165 sont clos : ils ne valident pas les nouveaux modules de #163.

GitHub connecté est la source de vérité. Commence par relire `AGENTS.md`, owner/repo, base/HEAD/SHA/tree, vrai diff complet, commits, reviews, threads et checks. Le dernier main observé par l'auteur est `755385e1e638365282e9cfccebdba4ce41fda451` ; c'est une référence historique à confirmer. Ne suppose pas qu'un clone local ou un ancien reçu correspond au distant. Sans Git réseau, utilise uniquement des objets au SHA confirmé, ou reconstruis le snapshot par le connecteur. Toute affirmation de test appartient au contenu exact exécuté.

Après chaque écriture : relis HEAD, contenu et diff affectés. Les corrections multi-fichiers doivent être atomiques si les primitives le permettent ; sinon travaille isolément et vérifie le résultat complet. Aucun test ancien ne valide automatiquement un nouveau HEAD. Un write ambigu n'est pas une publication confirmée.

## 1. Cartographier les obligations et les types de résultats

Lis intégralement `phase_discovery.py`, `phase_adaptive.py`, `phase_separator.py`, `phase_factored.py` et leurs dépendances réelles : `nonlinear_phase_bits.py`, `affine_phase.py`, `kraus_graph.py`, ressources et interprètes scalaires. Repère les helpers privés réutilisés et les hypothèses héritées.

Le contrat déclaré compare deux programmes dyadiques réels après un déphaseur sign/HMR réel, sur un support affine cohérent explicite. Toutes les sorties quantiques sont conservées et les résultats classiques oubliés. Il faut vérifier la restauration du déphaseur, l'égalité des fonctions de sortie, puis la constance du delta de phase sur les fibres de la signature **effective**, feedback compris. La préparation du support dans un circuit extérieur, l'utilisation sous contrôle cohérent et une extension à d'autres grammaires ne sont pas autorisées.

Vérifie séparément :
- `proved` : sources figées et nouvelle vérification finale, avec empreintes concordantes et délai originel restant.
- `different` : seulement un véritable témoin rejoué, de sorties différentes ou de même signature effective avec deltas différents.
- `dictionary_exhausted` : obstruction finie au dictionnaire fixé, pas une différence de canaux.
- `not_proved` : candidat fourni faux ou méthode structurelle insuffisante ; cela n'établit pas l'inéquivalence.
- `inconclusive`/`unsupported` : ressource ou dépendance manquante, sans certificat/témoin décisif conservé à tort.

Attention : la découverte factorisée peut manquer une compensation modulaire que le vérificateur agrégé accepte. Le test `2[a]+2[a XOR ab]=2[ab] mod4` doit rester un **refus sûr de la découverte**, pas un rejet du théorème ni une fausse réfutation.

## 2. Audit mathématique ciblé

### Dictionnaire fixe et adaptatif

Contrôle le système GF(2) à plusieurs bits de second membre, les pivots, substitutions, coefficients et provenances XOR. Les coefficients de phase modulo 2^k ne doivent jamais être traités comme un corps où tout pivot s'inverse.

Un contre-exemple doit soit augmenter le rang, soit fournir une obstruction valide, soit révéler une vraie collision de signature. Vérifie le rejeu de tous les échantillons d'une obstruction et la non-confusion entre une signature inaccessible et un échantillon réel. Dans `_complete`, l'ajout d'une colonne peut consommer une ancienne dépendance sans résoudre la ligne qui échouait : il faut contrôler le rang réel et continuer, sans assertion erronée ni acceptation anticipée. Compare `reuse_basis=True/False` sur les mêmes données, y compris les témoins et certificats, pas seulement les temps.

### Séparateurs et bornes

Reprends la preuve constructive de la borne `degré <= floor(log2 N)` pour N signatures distinctes, le choix de la moitié minoritaire et l'élimination des littéraux négatifs par parité. Contrôle le caractère distinct des mots, les types exacts, la parité de la colonne, sa nouveauté et le gain de rang. La minimalité par suppression n'est pas un minimum global.

Reproduis les deux frontières négatives : certains cas favorisent l'ancien glouton ; une politique uniquement à faible degré peut exiger `2^d` signatures pour un monôme de degré d sur un cube surjectif. Vérifie les hypothèses de cette borne et qu'elle n'est pas présentée comme une impossibilité générale d'apprentissage parcimonieux. Compare le corpus théorique fini et les vrais exemples de programmes sans additionner leurs garanties.

### Initialisation par les sources

Vérifie que `source_monomials=True` part des sources réellement extraites et de la signature effective, reconstruit exactement les produits par union de masques booléens, ne supprime pas les compensations globales et ne considère jamais une proposition comme une preuve. Les prédicats non monomiaux ignorés ne doivent pas produire un verdict de différence. Vérifie les limites de taille, les doublons et les valeurs par défaut inchangées.

### NOUVEAU : certificats factorisés et signatures mélangées

Le nouveau format est une somme modulaire pondérée de XORs de produits de formes affines de h. Un masque utilise le bit0 comme constante et le bit(j+1) pour h_j. Produit vide=1 ; XOR vide=0. Vérifie les types immuables exacts de chaque niveau, les bornes, coefficients canoniques, facteurs constants, répétitions, annulations, valeurs hors plage et masques malformés. Aucune variable libre du programme ne doit être introduite en dehors de h.

Contrôle `_span`, `_recover` et leur provenance sur les ANF effectives ; la reconstruction des formes affines ; la couverture booléenne des monômes ; l'interprétation des XORs versus les additions modulo 2^k ; les retenues et coefficients de poids différents. Vérifie les offsets, les signatures dépendantes/incomplètes et les images non surjectives. Une factorisation inconnue doit rester `not_proved`.

Le vérificateur de candidat doit reconstituer les sources indépendamment du reconnaisseur. Les formes affines peuvent être substituées par XOR d'ANF sources, mais les produits ne doivent pas être développés subrepticement. Tous les témoins SAT doivent être rejoués par l'interprète scalaire des sources ET l'évaluateur scalaire du certificat. Un candidat falsifié pour des canaux égaux n'est pas un témoin d'inéquivalence.

Refais l'argument de taille : pour `q_i=a_i*b_i`, `h_i=q_i XOR q_last`, `h_last=q_last`, le produit des q possède `2^(d-1)` termes ANF en h et une représentation factorisée à d facteurs. Les essais grands vérifient une représentation compacte, pas une simulation des `2^64` entrées. La reconnaissance et le format restent suffisants et non universels ; la nouvelle méthode ne remplace pas automatiquement la route CEGIS agrégée.

## 3. Attaques et oracles indépendants

Construis une nouvelle cohorte avec un générateur différent, puis conserve les données et seeds. Ne présente pas comme holdout une cohorte consultée pour corriger le code. Utilise un oracle exact de canal sur tous les opérateurs `|x><y|` de petites instances, pas seulement sur les entrées de base.

Inclure des positifs et négatifs, plusieurs précisions, angles négatifs/tours complets, sorties permutées ou altérées, déphaseurs à feedback, signatures non linéaires avec dépendances, supports décalés et singletons, ancillas empruntées, changements de base XOR denses, facteurs avec recouvrement et compensations entre termes. Vérifie les témoins littéraux même quand le moteur de recherche les annonce valides.

Attaques minimales : faux modèle SAT, résultat inconnu/interrompu, absence et exception de solveur ; faux séparateur ; mauvais facteur de source ; candidat et empreintes périmés ; faux succès de vérification fraîche ; mutation des objets après snapshot ; types sous-classés trompeurs ; structures récursives ; délai expiré au départ, pendant extraction/rejeu/nettoyage, et après une vérification fraîche positive ; plafonds nœuds/octets/termes hérités d'une session.

Un fallback implicite, une preuve sur un domaine élargi silencieusement ou un statut décisif qui survit à l'épuisement de ressources est bloquant. Vérifie aussi le contenu JSON/nested diagnostics après un refus : un résultat interne antérieur ne doit pas être réinterprétable comme une autorisation finale.

## 4. Ressources, performance et packaging

Le temps total inclut validation, snapshots, extraction, découverte, conversions, SAT, rejeu, vérification fraîche et destruction du solveur. Aucun sous-appel ne doit recréer un budget complet. Vérifie les bornes réellement appliquées et les refus explicites des unités non prises en charge. Statistiques de termes, clauses ou nœuds ne sont pas du RSS.

Reproduis les campagnes existantes avec toutes leurs lignes, dont les refus et régressions. Garde des budgets identiques et des répétitions intercalées. Pas de ratio de vitesse « succès contre inconclusive ». Vérifie le coût de la nouvelle préparation et la taille du certificat réellement sérialisé, les termes ANF seulement calculés théoriquement devant rester distingués de ceux effectivement matérialisés.

Teste une installation éditable avec natif/SAT/checkout requis, puis l'archive source extraite et la wheel hors checkout. Les fonctions de découverte peuvent utiliser des helpers privés en labs, mais pas dépendre de `tests`/`benchmarks` à l'exécution installée. Les imports doivent rester utilisables sans python-sat quand le solveur n'est pas requis ; les appels qui le nécessitent doivent refuser proprement son absence. Vérifie la documentation, l'index, le tableau labs, le CHANGELOG et les frontières de l'API.

## 5. Qualification et provenance

Commandes de départ, à compléter après lecture des workflows :

```bash
python -m pytest -q tests/test_phase_discovery.py tests/test_phase_discovery_adversarial.py tests/test_phase_adaptive.py tests/test_phase_adaptive_completion.py tests/test_phase_separator.py tests/test_phase_separator_integration.py tests/test_phase_separator_frontier.py tests/test_phase_separator_source.py tests/test_phase_factored.py
python -m benchmarks.phase_discovery --output evidence/phase-discovery.json
python -m benchmarks.phase_adaptive --output evidence/phase-adaptive.json
python -m benchmarks.phase_separator --output evidence/phase-separator.json
python -m benchmarks.phase_separator_frontier --output evidence/phase-separator-frontier.json
python -m benchmarks.phase_separator_source --output evidence/phase-separator-source.json
python -m benchmarks.phase_factored --output evidence/phase-factored.json
ruff check .
mypy
```

Exécute ensuite la suite complète avec les dépendances requises par le dépôt, et explique chaque catégorie de skip. Un job macOS annulé avant exécution n'est ni un test réussi ni un échec du code : il reste non validé et doit être relancé sur le contenu final avant la recommandation complète.

Pour chaque correction, conserve le test qui échoue sur l'ancien contenu et passe sur le nouveau ; n'affaiblis pas un test pour le rendre vert. Réévalue les benchmarks touchés et leurs assertions. Les jobs réussis avant modification sont historiques.

Télécharge les artefacts **des quatre qualifications de découverte/factorisation concernées**, pas seulement le statut Actions. Vérifie SHA-256 de chaque ZIP contre l'API, SHA/tree du checkout, propreté, parents du merge synthétique, toutes les empreintes de sources du manifeste et tous les indicateurs de succès. Les trois campagnes du workflow separator sont distinctes et doivent toutes être examinées. Relis la base et le HEAD avant de publier la décision.

## 6. Livrables et décision

Publie un rapport détaillé sur #163 et une synthèse sur l'issue d'audit. Pour chaque finding : gravité, fichier/ligne, SHA, hypothèse rompue, reproduction minimale, impact, correction et résultat avant/après. Documente aussi les résultats négatifs qui limitent l'adoption sans être des défauts de correction.

Donne les verdicts séparés `CORRECT_WITHIN_SCOPE`, `EXPERIMENTALLY_VALIDATED`, `REVIEWABLE`, `TECHNICALLY_MERGEABLE`, `AUTHORIZED_TO_MERGE`. L'autorisation de fusion reste **NON** pendant cette mission. Propose `ACCEPTABLE_LABS`, `CHANGES_REQUIRED` ou `DEFER` pour chaque composant et pour l'ensemble. La nouveauté scientifique, les performances externes et la validation de chargeurs réels restent des questions distinctes.

Si tout est favorable, prépare #163 pour décision avec son HEAD/tree exact et la CI correspondante ; pas de nouvelle PR d'assemblage nécessaire tant que l'ensemble est déjà dans cette branche. Ne supprime aucune branche et ne fusionne rien. Le rapport doit dire explicitement ce qui a été testé, corrigé, publié et ce qui ne l'a pas été.
