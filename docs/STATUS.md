# THNIYETNA v2 — état vérifié du projet

Audit en lecture seule du **15/10/2026 (16 h 45)**, sur le commit **`fb046eb`** (branche `main`).
Aucune donnée ni aucun code n'ont été modifiés ; le LLM n'a pas été appelé pendant l'audit (pas d'appel à
`/assistant/ask` ni à `/assistant/intervention`).

## a) Résumé

1. La pile Docker tourne. `db` et `api` sont *healthy* ; `osrm`, `web` et `m2-worker` sont démarrés (sans healthcheck) ;
   `perception-worker` (M1) et `mlflow` ne sont pas lancés.
2. **M2** fonctionne de bout en bout : modèle `2026.10.11-2054` chargé, 675 segments notés et 192 prévisions par
   gouvernorat (24 × 8 jours). Faute d'événements M1, tout le risque absolu est faible (max 0,183934).
3. **M1 est bloqué** : il n'y a aucun checkpoint YOLO dans `models/`. Le worker n'est pas lancé, 2 jobs attendent
   (`queued`) depuis le 14/10, et la base contient 0 événement routier.
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
| Détection de défauts (YOLO, RDD2022) | ❌ | `models/` ne contient que `m2/` ; `models/README.md` : aucun poids fourni | Entraîner/évaluer YOLO26n/s et YOLO11n (`ml/perception/train_detector.py`), copier `road-damage-yolo26n.pt` |
| Worker de perception (file de jobs) | ❌ | `perception-worker` absent de `docker compose ps` (profil `m1`) ; base : 2 `perception_jobs` en `queued` depuis le 14/10 18:53 UTC | Lancer le profil `m1` une fois le checkpoint présent |
| Code du pipeline (vidéo, GPS, fusion d'observations) | 🟡 | `ml/perception/tests/test_core.py` : 2 tests réussis ; pas d'exécution réelle | Mesures mAP, latence, jeu pilote tunisien (`docs/work-packages/M1.md`) |
| Événements routiers + liste superviseur | 🟠 | `GET /perception/events` → 200, 0 ligne ; `road_events` = 0, `road_observations` = 0 | Données réelles ; validation (`PATCH …/validate`) non testée en direct (écriture) |
| Sessions d'inspection (start / heartbeat / stop) | 🟠 | Code + API (`perception/router.py`) ; `GET /perception/inspections` → 200, 0 session | Aucune page web pour le véhicule d'inspection ; non testé en direct (écriture) |

### M2 — Prédiction du risque

| Fonctionnalité | Statut | Preuve | Ce qui reste |
|---|---|---|---|
| Modèle chargé par l'API | ✅ | `GET /prediction/model` → `status ok`, version `2026.10.11-2054`, classifieur `logreg` | — |
| Prévisions par gouvernorat | ✅ | `GET /prediction/governorates` → 192 lignes nommées, 24 gouvernorats, 8 jours (15→22/10), 116 alertes | Vérifier si ce taux d'alerte élevé est utile en pratique |
| Score de risque par segment (RiskScore 1.1.0) | ✅ | `GET /prediction/segments` → 675 segments, max 0,183934 ; `?min_level=medium` → 0 ; `?top=0.05` → 34 | Un risque absolu plus contrasté demande des événements M1 |
| Priorités d'entretien | ✅ | Base : 271 P3 et 404 P4, tous `no_observed_defect` / `low` | Pas de P1/P2 sans défaut observé |
| Worker M2 (passe de scoring) | ✅ | `m2-worker` démarré ; scores créés le 15/10 12:36 UTC, valables jusqu'au 16/10 | — |
| Données d'entraînement | ✅ | Base : `accident_records` ≈ 69 394, `weather_observations` ≈ 1 652, 24 `admin_areas` | L'export accidents s'arrête au 27/09/2026 (`docs/M2_MODEL_CARD.md`) |
| Pipeline d'entraînement | 🟡 | `ml/prediction/tests/test_m2_core.py` : 34 tests réussis ; carte `docs/M2_MODEL_CARD.md` (test PR-AUC 0,6111) | — |
| Expérience météo par gouvernorat | ✅ | `docs/M2_WEATHER_EXPERIMENT.md` : résultat négatif, modèle de base conservé (14/10) | — |
| Modèle d'état « mode B » | ❌ | Bloqué : nécessite des défauts M1 étiquetés (`condition_model.py`, CLAUDE.md) | Après M1 |
| Suivi MLflow | 🟠 | Service `mlflow` (profil `ml`) non lancé ; l'expérience du 14/10 a utilisé des enregistrements JSON | Lancer le profil `ml` si besoin |

### M3 — Routage

| Fonctionnalité | Statut | Preuve | Ce qui reste |
|---|---|---|---|
| Calcul d'itinéraire OSRM (Bizerte) | ✅ | `POST /routing/route` (centre → sud) → 200, 5 655,5 m, 512,7 s, `normal_route` ; OSRM direct `:5002` → `Ok` | — |
| Coût tenant compte du risque + déviation | 🟡 | `tests/test_routing_m2_risk.py` : 4 réussis (image `api`) ; en direct, risque 0,004 donc aucune déviation | Démonstration avec un segment réellement à risque |
| Lignes officielles et affectations | 🟠 | `GET /routing/official-routes` → 0 ; `GET /routing/assignments` → 0 | Créer de vraies lignes / bus / affectations (non testé : écriture) |
| Alerte de déviation conducteur | 🟡 | Couvert par `test_routing_m2_risk.py` ; `GET /platform/alerts` (conducteur) → 200, 5 lignes (`risk.batch_updated`) | Démonstration en direct avec une affectation |
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
| Fiche d'intervention | ✅ | Vérifiée en direct le 15/10 avant l'audit (segment P3 OSM-100663969, 58,5 s puis 13,8 s) ; tests `test_rag_api.py` 8/8 et `test_rag_intervention.py` 6/6 | Recette d'un segment avec défaut (aucun en base) |
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
| M1 n'a aucun checkpoint : aucune détection automatique possible | `models/README.md`, `docker compose ps` |
| Sans événements M1, le risque absolu M2 est faible partout (max 0,183934) ; les priorités sont P3 (271) ou P4 (404), toutes « aucun défaut observé » | Base `risk_scores`, `GET /prediction/segments` |
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
| 1 | Entraîner et évaluer le détecteur M1 (RDD2022, YOLO26n/s, YOLO11n), déposer le checkpoint, lancer le profil `m1` et traiter les 2 jobs en attente | L | **Oui** (jeu RDD2022 de plusieurs Go, torch / ultralytics) |
| 2 | Valider le jeu de questions RAG et les étiquettes manuelles (Sirine) | S | Non |
| 3 | Corriger l'heuristique des titres, relancer `rag.ingest --contexts`, puis évaluer `fts_french` → `chunk_context` → `confidence_gate` → `numbers_rule` (+ `combined_gemma4` si la RAM le permet) | M | Non |
| 4 | Recette manuelle des écrans dans un navigateur (citoyen, conducteur, deux superviseurs, Assistant, impression de la fiche) | S | Non |
| 5 | Saisir de vraies lignes, bus et affectations pour démontrer la déviation conducteur (M3/M4) | S | Non |
| 6 | Après M1 : événements réels → priorités P1/P2 → fiche avec défaut → entraînement du modèle d'état « mode B » | M | Non (après le n° 1) |
| 7 | Faire tourner les tests FastAPI dans la CI / l'image de test et vérifier les exécutions GitHub | S | Petit téléchargement (pytest) |
| 8 | Réactiver un calque de risque lisible sur la carte | S | Non |
| 9 | Importer les noms OSM manquants des segments | S | Peut-être (selon l'extrait OSM déjà présent) |
| 10 | Tester un modèle de langage plus grand si la qualité reste insuffisante | M | **Oui** si autre que `gemma4` (déjà présent) |

## f) Comment lancer le projet

```powershell
# 1. Ollama sur l'hôte Windows (modèles déjà présents : llama3.2:3b, nomic-embed-text), écoute sur toutes les interfaces
$env:OLLAMA_HOST = "0.0.0.0"; ollama serve
# 2. Pile complète (db, api, web, osrm, worker M2)
docker compose -f docker-compose.yml -f ml/prediction/docker-compose.m2.yml --profile m2 up -d --build
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
