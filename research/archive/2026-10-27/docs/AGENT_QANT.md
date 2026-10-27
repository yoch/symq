# Mission pour l'agent travaillant sur qant — consolidation et portage

Ce dossier est une proposition **non fusionnée**, dont le code a été exécuté
hors dépôt. L'agent doit partir de l'état courant du vrai GitHub distant,
relire `AGENTS.md`, `STATE.md`, `agents/ownership.yml`, et respecter les
branches/propriétaires de fichiers. Ne jamais présumer que `master` est encore
sur la photographie relevée le 27/10/2026 (`48bd7edd...`).

## But

Rendre les certificats symboliques plus rapides **sans changer leur verdict,
leur contrat d'entrée, les phases HMR ni le nettoyage des ancillas**.

## Expériences à faire en premier

1. Confirmer sur un SHA exact les contenus de `experiments/dqi/gf_product_certificate.py`,
   `experiments/dqi/discrepancy_certificate.py`, `src/qant/certificate.py`,
   `src/qant/blocks/exact_domain.py` et les fichiers de campagnes DQI pertinents.
2. Qualifier le rôle/propriétaire de `experiments/dqi/**` avant toute modification.
   Réaliser d'abord un banc **lecture seule** sur un `worktree` isolé ou une
   expérience indépendante dans le dossier autorisé.
3. Essayer **l'optimisation simple** `symmetric_difference_update` sur `CX`
   (contrôles et cibles distincts). C'est généralement la meilleure première
   modification. Ne jamais modifier `a` quand il appartient à un autre fil.
4. Instrumenter le nombre de monômes par fil et par porte (`max_target_monomials`,
   `total_alive_monomials`, degré maximal et nombre de mesures).
5. Comparer trois backends sur **le même fragment et le même SHA** : ANF set
   original, set en place, et `AutoZDDState` (bascule à ≥850 monômes, ou garde
   de ressources). Conserver le modèle de phase du vérificateur historique.
6. Vérifier de manière indépendante sorties, ancillas et phase sur toutes les
   entrées de petits fragments puis sur le domaine réel lorsque possible. Le
   PASS Kickmix reste obligatoire pour tout nouveau hash de circuit.
7. Option : sur un checkout local autorisé, exécuter
   `PYTHONPATH=. python tools/replay_qant_fixture.py /path/.../84-core-forward.kmx --out result_NEW.json`.
   Ce résultat **ne prouve pas** le contrat quantique, puisque q0..q23 libres
   sont une hypothèse indépendante. Il sert à comparer deux moteurs symboliques.

## Conditions d'arrêt

- Le fragment réel ne respecte pas l'alphabet de portes ou la sémantique de phase
  du moteur : rejeter le fragment (`UNSUPPORTED`), ne pas le convertir silencieusement.
- Si `fast_set` ne fait pas mieux sur le certificat complet, ne pas intégrer pour
  un microgain isolé.
- Si `AutoZDD` ne réduit pas le temps complet ou la mémoire et augmente les
  allocations, s'en tenir à `fast_set` ; conserver le résultat négatif.
- Un gain de calcul symbolique n'est pas une réduction Toffoli/Q et ne justifie
  aucune soumission Kaggle.
- Respecter les limites de temps, RSS et concurrence du dépôt ; aucun GPU
  payant, aucune modification des vérificateurs officiels, aucun push dans
  `master` ni soumission Kaggle sans autorisation explicite.

## Preuves attendues

- Ref exact, Git blob SHA de chaque entrée, digest de l'outil, versions Python,
  dépendances, architecture CPU, GC et nombre de répétitions.
- Au moins une vérification indépendante complète sur un domaine restreint,
  mutation négative détectée, logs de tests sans ambiguïté.
- Temps **séparé** du calcul symbolique, génération, comparaison finale et
  `tracemalloc`, avec pics mémoire et timeout. Les mesures sous 1 ms sont bruitées.
- Tests d'équivalence avant/après sur les vrais appels aux certificats, pas
  uniquement sur `src.optimized` ou un programme artificiel.
- PR isolée et contrôles définis par les règles du repo. Ne pas réutiliser un
  PASS d'un ancien SHA.

## Fichiers à consulter

- `README.md` ; `docs/CORPORA_RECENTS.md` ; `docs/COMPARAISON_EXISTANT.md`.
- `src/optimized.py`, `src/zdd.py`, `tests/test_symbolic.py`.
- `benchmarks/run_corpus.py`, `benchmarks/selector_sensitivity.py`.
- `results/bench_public_final_v3.json` et `results/selector_sensitivity.json`.

## Limite de publication

L'idée ZDD est une antériorité établie (PolyBoRi). Le choix adaptatif n'est pour
l'instant qu'une heuristique empirique choisie sur cinq circuits. Viser
**un algorithme robuste de choix de représentation à contrats vérifiables** et
une campagne large sur circuits réels 2026 comprenant HMR, plutôt qu'un
article « nous avons inventé les ZDD pour l'ANF ».
