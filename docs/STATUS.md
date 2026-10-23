# THNIYETNA v2 — état vérifié du projet

Audit en lecture seule du **15/10/2026 (16 h 45)**, sur le commit **`fb046eb`** (branche `main`).
Aucune donnée ni aucun code n'ont été modifiés ; le LLM n'a pas été appelé pendant l'audit (pas d'appel à
`/assistant/ask` ni à `/assistant/intervention`).

> **Mise à jour du 23/10/2026 (M1).** Les lignes M1 et celles marquées *(23/10)* ont été mises à jour après la mise
> en service du détecteur pré-entraîné `yolo26s-rdd2022-dronefreak` et une boucle complète citoyen → M1 → validation
> → M2 → fiche d'intervention. Détails : `docs/M1_MODEL_CARD.md`. Le reste du document reflète toujours l'audit du 15/10.
>
> **Mise à jour du 23/10/2026 (M3).** Graphe OSRM étendu à tout le gouvernorat ; données de démo
> (`scripts/seed_demo.py`) ; règle de déviation corrigée (mesure vraie des dangers, alternative obligée d'éviter les
> dangers déclencheurs, recherche autour des dangers, avertissement sans alternative). Décision : `docs/DECISIONS.md` (D-001).

## a) Résumé

1. La pile Docker tourne. `db` et `api` sont *healthy* ; `osrm`, `web` et `m2-worker` sont démarrés (sans healthcheck) ;
   `perception-worker` (M1) et `mlflow` ne sont pas lancés.
2. **M2** fonctionne de bout en bout : modèle `2026.10.11-2054` chargé, 675 segments notés et 192 prévisions par
   gouvernorat (24 × 8 jours). Faute d'événements M1, tout le risque absolu est faible (max 0,183934).
3. **M1 fonctionne (23/10)** avec un modèle public pré-entraîné (YOLO26s RDD2022, dronefreak, AGPL-3.0) sur CPU.
   Boucle vérifiée en direct : 1 signalement citoyen → 1 événement validé → le segment OSM-100663969 passe de
   faible / P3 à **moyen / P2 / « poor »**. Mais les nids-de-poule des photos rapprochées ne sont pas détectés (0/7 sur le pilote).
4. **M3/M4/M5** : routage OSRM, authentification par rôles, temps réel (SSE) et application web sont vérifiés en direct.
   En revanche, il n'y a encore ni ligne officielle, ni bus, ni affectation, donc pas de démonstration de déviation.
5. **Assistant RAG** : 4 guides (582 extraits), interface parties A et B en place. Qualité des réponses de
   llama3.2:3b : au mieux 9 réponses correctes sur 16 questions répondables (`prompt_v2`), et 5 variantes restent à évaluer.

Légende des statuts : ✅ Vérifié en direct · 🟡 Testé (tests auto) mais pas vérifié en direct · 🟠 Partiel ·
❌ Pas commencé / bloqué.

**Preuves utilisées pendant l'audit :**
- `pytest -q` (racine, `ml/.venv`) : **74 réussis, 3 ignorés**. Les 3 fichiers ignorés demandent fastapi :
  `test_auth_staff`, `test_rag_api`, `test_routing_m2_risk`.
- Ces 3 fichiers ont été exécutés à part dans l'image `api` (pytest n'y est pas installé ; un petit lanceur
  équivalent a été utilisé) : **28 réussis sur 28**.
- Appels API en direct à travers nginx (`http://web/api`) avec les comptes de démarrage. Le mot de passe a été lu
  dans l'environnement, jamais affiché.
- Comptages directs en base (PostgreSQL) et `docker compose ps`.

## b) Tableau par module

### M1 — Perception

| Fonctionnalité | Statut | Preuve | Ce qui reste |
|---|---|---|---|
| Détection de défauts (YOLO, RDD2022) | 🟠 | *(23/10)* `models/road-damage-yolo26s.pt` = modèle public dronefreak (SHA-256 dans `models/README.md`) ; `check_m1_model.py` : 4 classes = `RDD_CLASS_MAP` ; métriques publiées **par l'auteur** (mAP50 61,27 %, sur son propre découpage) ; CPU p50 140 ms, 4,7 img/s (i7-1255U) ; pilote de 14 photos : 0/7 nid-de-poule détecté, fissure détectée, 1 faux positif sur 5 routes intactes | Jeu pilote de Bizerte pris depuis un véhicule et étiqueté → mAP local ; ré-entraînement si le rappel des nids-de-poule reste faible (`docs/M1_MODEL_CARD.md`) |
| Worker de perception (file de jobs) | ✅ | *(23/10)* `perception-worker` lancé (profil `m1`, CPU, torch `+cpu`) ; job citoyen traité en 1,9 s. Les 2 jobs du 14/10 sont marqués `failed` avec la raison (même photo de banque d'images envoyée 5 fois par le compte de test `root`, hors segment) ; rien n'a été supprimé | Healthcheck du worker |
| Code du pipeline (vidéo, GPS, fusion d'observations) | 🟡 | `ml/perception/tests/test_core.py` : 5 tests ; chemin image vérifié en direct (23/10) ; vidéo + GPS non exécutés en réel | Session d'inspection réelle avec vidéo |
| Événements routiers + liste superviseur | ✅ | *(23/10)* 1 observation + 1 `road_event` (alligator_crack, conf 0,354, sévérité 0,7264) sur OSM-100663969 ; `PATCH /perception/events/{id}/validate` (equipment.supervisor) → 200, `validated` | Plus de données réelles |
| Sessions d'inspection (start / heartbeat / stop) | 🟠 | Code + API (`perception/router.py`) ; `GET /perception/inspections` → 200, 0 session | Aucune page web pour le véhicule d'inspection ; non testé en direct (écriture) |

### M2 — Prédiction du risque

| Fonctionnalité | Statut | Preuve | Ce qui reste |
|---|---|---|---|
| Modèle chargé par l'API | ✅ | `GET /prediction/model` → `status ok`, version `2026.10.11-2054`, classifieur `logreg` | — |
| Prévisions par gouvernorat | ✅ | `GET /prediction/governorates` → 192 lignes nommées, 24 gouvernorats, 8 jours (15→22/10), 116 alertes | Vérifier si ce taux d'alerte élevé est utile en pratique |
| Score de risque par segment (RiskScore 1.1.0) | ✅ | *(23/10)* 675 segments ; OSM-100663969 : 0,1837 → **0,3940 (medium)** après l'événement M1 validé (composante état 0,2576, facteur principal `m1:road_condition`) ; les 674 autres `low` | Un risque absolu plus contrasté demande plus d'événements M1 |
| Priorités d'entretien | ✅ | *(23/10, démo rééquilibrée)* 4 P2, 267 P3, 404 P4 ; 3 segments `medium` (dont OSM-125567491, porteur des 2 événements de démo de L1, 0,344) | — |
| Prise en compte des événements du jour | ✅ | *(23/10)* Corrigé : `score.py` coupait les événements à minuit, donc un événement du jour n'était compté qu'au passage du lendemain. Maintenant, la limite est l'heure du calcul (`segment_cutoff`), et `--as-of` garde minuit. Test `test_same_day_m1_event_counts_in_todays_pass` ; image `m2-worker` reconstruite | — |
| Worker M2 (passe de scoring) | ✅ | `m2-worker` démarré ; scores créés le 15/10 12:36 UTC, valables jusqu'au 16/10 | — |
| Données d'entraînement | ✅ | Base : `accident_records` ≈ 69 394, `weather_observations` ≈ 1 652, 24 `admin_areas` | L'export accidents s'arrête au 27/09/2026 (`docs/M2_MODEL_CARD.md`) |
| Pipeline d'entraînement | 🟡 | `ml/prediction/tests/test_m2_core.py` : 34 tests réussis ; carte `docs/M2_MODEL_CARD.md` (test PR-AUC 0,6111) | — |
| Expérience météo par gouvernorat | ✅ | `docs/M2_WEATHER_EXPERIMENT.md` : résultat négatif, modèle de base conservé (14/10) | — |
| Modèle d'état « mode B » | ❌ | Nécessite ≥ 50 défauts M1 positifs (`condition_model.py`, CLAUDE.md) ; 1 événement en base (23/10) | Accumuler des événements validés |
| Suivi MLflow | 🟠 | Service `mlflow` (profil `ml`) non lancé ; l'expérience du 14/10 a utilisé des enregistrements JSON | Lancer le profil `ml` si besoin |

### M3 — Routage

| Fonctionnalité | Statut | Preuve | Ce qui reste |
|---|---|---|---|
| Calcul d'itinéraire OSRM (Bizerte) | ✅ | *(23/10)* Graphe reconstruit pour tout TN-23 (`scripts/osm-clip-bizerte.sh`) : Bizerte → Menzel Bourguiba 23,6 km, Mateur 40,5 km, Ras Jebel 36,6 km, Zarzouna 3,1 km (avant : île séparée / hors graphe) | OSRM ne renvoie aucune alternative native sur ces trajets : toutes viennent de la recherche de détours de M3 |
| Coût tenant compte du risque + déviation | ✅ | *(23/10)* Règle corrigée (D-001) : distance vraie PostGIS, alternative éligible seulement si elle évite à > 105 m chaque danger déclencheur, détours cherchés autour des dangers ; seuils 0,42 / 0,12 inchangés. `tests/test_routing_event_reroute.py` 15 + `test_routing_m2_risk.py` 5 réussis (image `api`). Démo : L1 dévie (0,726 → 0,024, 28,2 km, danger le plus proche à 362 m) | L1 et L2 partagent RN11 : un danger contournable sur L1 est aussi sur L2 |
| Lignes officielles et affectations | 🟡 | *(23/10)* 4 lignes de démo `DEMO-L1…L4` et leurs affectations, créées par l'API (`scripts/seed_demo.py`) | Lignes réelles SRTB |
| Alerte conducteur (déviation / avertissement) | ✅ | *(23/10, démo rééquilibrée)* Calculé par M3 : L1 `driver.reroute.alert` (« 2 danger(s) sur le trajet initial, 0 sur l'alternative ; risque 73 % → 2 % »), L2 `driver.route.warning` (3 dangers, risque 80 %, aucune alternative éligible), L3 / L4 aucune alerte (risque 14 % / 0 %). Une seule alerte active par conducteur et ligne : un nouveau contrôle identique la rafraîchit (« Confirmée n× »), vérifié en direct et en navigateur headless (`/driver`, `/driver/alerts`) | Temps de réponse 0,02–1,7 s par contrôle de ligne |
| Géocodage | ✅ | `GET /routing/geocode?q=Corniche` → 2 résultats (Nominatim public, nécessite Internet) | — |

### M4 — Plateforme web

| Fonctionnalité | Statut | Preuve | Ce qui reste |
|---|---|---|---|
| Application servie (nginx) | ✅ | `/`, `/login`, `/citizen`, `/driver`, `/ministry/equipment`, `/ministry/transport` → 200 sur `:8081` | — |
| Carte (segments, signalements) | ✅ | `GET /platform/map` → 675 segments, 2 signalements, 0 événement, 0 ligne | Calque de risque désactivé volontairement (`MapCanvas.jsx`, l. 10) |
| Tableau de bord Équipement | ✅ | `GET /platform/dashboard/equipment` → 2 signalements ouverts, 0 détection, 0 inspection active | — |
| Tableau de bord Transport | ✅ | `GET /platform/dashboard/transport` → 0 ligne, 0 bus, 0 affectation | Données de flotte |
| Parcours citoyen (signalement photo, suivi) | 🟠 | Pages et API présentes (code) ; 1 compte citoyen en base, non utilisé (mot de passe inconnu, écriture) | Parcours à vérifier en direct |
| Parcours conducteur | 🟠 | Connexion `driver.srtb` ✅ ; `GET /routing/driver/me` → 0 (aucune affectation) | Affectation pour démontrer la carte et la déviation |
| Temps réel (SSE) | ✅ | `GET /api/realtime/stream` → `event: connected` + keepalive | — |
| Interface non vérifiée par clic | 🟠 | Aucun navigateur automatisé pendant l'audit : seuls les routes et le bundle ont été vérifiés | Recette manuelle des écrans |

### M5 — Fondation et intégration

| Fonctionnalité | Statut | Preuve | Ce qui reste |
|---|---|---|---|
| Pile Docker Compose | ✅ | `docker compose ps` : db, api *healthy* ; osrm, web, m2-worker démarrés | Healthchecks pour osrm / web / m2-worker |
| Santé et dépendances | ✅ | `GET /system/ready` → database, postgis, media_storage = true ; `/health` → ok | — |
| Schéma (Alembic) | ✅ | Base : `alembic_version` = `0006_rag_chunk_context` | — |
| Authentification JWT et rôles | ✅ | 4 connexions de démarrage → 200 ; conducteur → tableau Équipement **403** ; anonyme → signalements **401** ; `test_auth_staff.py` 16/16 (image `api`) | — |
| Gestion des comptes par ministère | ✅ | `GET /auth/staff` → 2 comptes pour chaque ministère | — |
| Stockage média local | ✅ | `GET /system/storage` → `local-volume`, dossiers images / videos / frames / exports | — |
| File de notifications (outbox) | ✅ | Base : 8 notifications `pending` (2 complaint.created, 1 complaint.status, 5 risk.batch_updated), lues par le SSE | — |
| Intégration continue | 🟠 | `.github/workflows/ci.yml` présent ; exécutions non vérifiées (`gh` absent) ; `main` local en avance de 3 commits sur `origin/main` avant cet audit | Vérifier les exécutions CI sur GitHub |
| Tests FastAPI dans `pytest -q` | 🟠 | Ignorés dans `ml/.venv` (fastapi absent) ; réussis dans l'image `api` via un lanceur sans pytest | Installer pytest dans l'image de test ou la CI |

### RAG / Assistant

| Fonctionnalité | Statut | Preuve | Ce qui reste |
|---|---|---|---|
| Corpus indexé (guides terrain seulement) | ✅ | `GET /assistant/status` → 4 documents, 582 extraits ; Ollama joignable, `llama3.2:3b` et `nomic-embed-text` présents | Ajouter un guide utilisateur dans `data/rag/corpus/` |
| Question / réponse citée (`/assistant/ask`) | ✅ | Vérifié en direct le 15/10 avant l'audit (35,7 s, 4 sources avec extraits ; CLAUDE.md) ; **pas rappelé pendant l'audit** | Qualité des réponses (voir limites) |
| Fiche d'intervention | ✅ | *(23/10)* Segment avec défaut OSM-100663969 (P2) : 200 en 100 s ; le Constat cite la détection M1 validée et le signalement ; les 3 sections de conseils sont marquées `uncited` (llama3.2:3b sans [n]) | Citations des conseils |
| Onglet « Assistant » et fiche imprimable | 🟠 | Bundle servi contenant les libellés et la règle `@media print` ; pas de clic en navigateur | Recette manuelle |
| Évaluation | 🟠 | `docs/RAG_EVALUATION.md` : 4 variantes exécutées et étiquetées ; 5 non exécutées | Lancer `combined_gemma4`, `fts_french`, `chunk_context`, `confidence_gate`, `numbers_rule` |
| Options A.6 (FTS français, contexte, porte de confiance, règle des nombres) | 🟡 | Tests unitaires ; index cohérent (582/582 `embedding_ctx`) ; non évaluées | Corriger l'heuristique des titres avant `chunk_context` |
| Journal des requêtes | ✅ | Base : `rag_queries` = 7, dernière le 15/10 15:43 UTC | — |

## c) Tableau par acteur (application web, aujourd'hui)

| Acteur | Ce qu'il peut faire | Vérification |
|---|---|---|
| Citoyen | Créer un compte, voir la carte, calculer un itinéraire avec alternative plus sûre, signaler un défaut avec photo et GPS, suivre ses signalements | Pages servies et API de carte / itinéraire en direct ; inscription et signalement **non testés en direct** (écritures) |
| Conducteur (`driver.srtb`) | Voir sa ligne affectée, demander le meilleur itinéraire suivant, lire ses alertes | Connexion ✅ ; alertes 5 ✅ ; **aucune ligne affectée**, donc carte et déviation non démontrables |
| Superviseur Équipement | Traiter les signalements, valider les détections M1, suivre les inspections, voir les priorités d'entretien M2, fiche d'intervention, onglet Assistant, gérer les comptes de son ministère | API en direct ✅ (tableau, signalements, détections, inspections, comptes, assistant) ; aucune détection à valider (0 en base) |
| Superviseur Transport | Voir les prévisions M2 par gouvernorat et les segments surveillés, gérer lignes, bus et affectations, onglet Assistant, gérer les comptes | API en direct ✅ (tableau, véhicules, affectations, comptes, assistant) ; 0 ligne, 0 bus |
| Véhicule d'inspection (`inspection.vehicle`) | **Aucune page web** : rôle utilisé par l'API seulement (démarrage / position / arrêt d'inspection, envoi de vidéo) | Connexion ✅ ; parcours **non testé** (écritures, pas d'appareil) |

## d) Limites connues

| Limite | Source |
|---|---|
| *(23/10)* M1 utilise un modèle public non entraîné sur des routes tunisiennes ; nids-de-poule des photos rapprochées non détectés (0/7), toutes les confiances < 0,40 ; aucun mAP local ; la sévérité est un indicateur visuel | `docs/M1_MODEL_CARD.md` |
| *(23/10)* Poids sous licence AGPL-3.0 (obligations en cas de service réseau public) | `docs/M1_MODEL_CARD.md`, `models/README.md` |
| Un seul événement M1 en base : le risque absolu M2 reste faible ailleurs (674 segments `low`) | Base `risk_scores` |
| Pas de coordonnées GPS dans les accidents : le risque par segment est une répartition de l'exposition, pas un modèle de point noir | `docs/M2_MODEL_CARD.md` |
| Dans un même gouvernorat, la date d'un accident est presque imprévisible (ROC-AUC médian 0,524) ; l'historique porte l'essentiel du signal | `docs/M2_MODEL_CARD.md`, `docs/M2_WEATHER_EXPERIMENT.md` |
| L'export des accidents s'arrête au 27/09/2026 (retard sur la date de scoring) | `docs/M2_MODEL_CARD.md` |
| 116 des 192 prévisions par gouvernorat sont en alerte | `GET /prediction/governorates` |
| Qualité des réponses RAG avec llama3.2:3b : au mieux 9 correctes / 2 partielles / 3 fausses sur 16 questions répondables (`prompt_v2`). Il copie mal les nombres (ex. « 0 °C » au lieu de > 10 °C pour l'enrobé chaud) | `docs/RAG_EVALUATION.md`, CLAUDE.md (vérification du 15/10) |
| Les étiquettes de correction de l'évaluation RAG sont manuelles (Claude), à valider ; le jeu de questions est un brouillon | `data/rag/eval/questions.jsonl`, `docs/RAG_EVALUATION.md` |
| Le modèle omet parfois les citations [n] ; c'est signalé à l'écran (« Sans citation ») | `backend/rag/intervention.py`, test `test_parse_sections_headings_variants_and_missing` |
| Lenteur du LLM sur CPU : 30 à 60 s par réponse (timeout nginx porté à 300 s) | `frontend/nginx.conf`, vérification du 15/10 |
| L'heuristique des titres de section (contexte des extraits) ignore les titres numérotés répétés et prend des textes de panneaux pour des titres | CLAUDE.md (A.6), `backend/rag/context.py` |
| Calque de risque désactivé sur la carte | `frontend/src/components/MapCanvas.jsx` l. 10 |
| Seuls 307 segments sur 675 ont un nom | Base `road_segments` |
| Les tests FastAPI sont ignorés par `pytest -q` hors image `api` | `pytest -q -rs` |

## e) Ce qui reste à faire (par priorité)

| # | Tâche | Taille | Wi-Fi ? |
|---|---|---|---|
| 1 | *(23/10, en partie fait)* Modèle pré-entraîné en service. Reste : jeu pilote de Bizerte (photos prises depuis un véhicule, étiquetées) → mAP local ; ré-entraîner (RDD2022 + images locales) si le rappel des nids-de-poule reste faible | L | **Oui** pour le ré-entraînement |
| 2 | Valider le jeu de questions RAG et les étiquettes manuelles (Sirine) | S | Non |
| 3 | Corriger l'heuristique des titres, relancer `rag.ingest --contexts`, puis évaluer `fts_french` → `chunk_context` → `confidence_gate` → `numbers_rule` (+ `combined_gemma4` si la RAM le permet) | M | Non |
| 4 | Recette manuelle des écrans dans un navigateur (citoyen, conducteur, deux superviseurs, Assistant, impression de la fiche) | S | Non |
| 5 | *(23/10 : démo L1 déviation / L2 avertissement / L3-L4 normal)* Saisir les vraies lignes SRTB | S | Non |
| 6 | *(23/10 : boucle démontrée sur 1 segment, P2 + fiche avec défaut)* Accumuler des événements validés, puis entraîner le modèle d'état « mode B » (≥ 50 positifs) | M | Non |
| 7 | Faire tourner les tests FastAPI dans la CI / l'image de test et vérifier les exécutions GitHub | S | Petit téléchargement (pytest) |
| 8 | Réactiver un calque de risque lisible sur la carte | S | Non |
| 9 | Importer les noms OSM manquants des segments | S | Peut-être (selon l'extrait OSM déjà présent) |
| 10 | Tester un modèle de langage plus grand si la qualité reste insuffisante | M | **Oui** si autre que `gemma4` (déjà présent) |

## f) Comment lancer le projet

```powershell
# 1. Ollama sur l'hôte Windows (modèles déjà présents : llama3.2:3b, nomic-embed-text), écoute sur toutes les interfaces
$env:OLLAMA_HOST = "0.0.0.0"; ollama serve
# 2. Pile complète (db, api, web, osrm, worker M2, worker M1 — poids : python scripts/download_m1_model.py)
docker compose -f docker-compose.yml -f ml/prediction/docker-compose.m2.yml --profile m2 --profile m1 up -d --build
# 3. Indexer les guides du RAG (ignore les fichiers inchangés)
docker compose -f docker-compose.yml -f ml/prediction/docker-compose.m2.yml --profile m2 exec api python -m rag.ingest
# 4. Vérifier l'état des services
docker compose -f docker-compose.yml -f ml/prediction/docker-compose.m2.yml --profile m2 ps
# 5. Tests
.\ml\.venv\Scripts\python.exe -m pytest -q
```

Sur une base vide, les données M2 s'ingèrent une fois avec `python -m prediction.jobs.ingest all …` (voir CLAUDE.md, runbook M2 §2).

| Service | URL |
|---|---|
| Application web | http://localhost:8081 |
| API (documentation interactive) | http://localhost:8000/docs |
| OSRM | http://localhost:5002 |
| PostgreSQL (depuis l'hôte) | `localhost:5433`, base `thniyetna` |

Comptes de démarrage : `equipment.supervisor`, `transport.supervisor`, `driver.srtb`, `inspection.vehicle`
(mot de passe : `BOOTSTRAP_PASSWORD` du fichier `.env`, non reproduit ici).
