# Décisions du projet THNIYETNA

Registre des décisions qui changent un comportement du système. Une entrée par décision : contexte, décision,
conséquences, et qui a décidé / qui doit être informé.

---

## D-001 — M3 : mesure des dangers et règle d'évitement des déviations

- **Date :** 23/10/2026
- **Décidé par :** Sirine Tiouajni (cheffe de projet)
- **À informer :** Iheb
- **Code :** `backend/routing/router.py` ; tests `tests/test_routing_event_reroute.py`
- **Commits :** `11ee65a` (mesure), `2d8fe84` (éligibilité), `d2b73b7` (recherche autour des dangers),
  `30a986c` + `1e3b6c2` (temps de réponse), puis le commit « avertissement sans alternative »

### Contexte

Une vérification de bout en bout du 23/10 (4 lignes de démo + un test contrôlé sur une copie de la ligne 1) a montré
qu'une alerte de déviation pouvait recommander un itinéraire **passant à 0 m du danger** qui l'avait déclenchée :
1. la distance danger–itinéraire était mesurée aux **sommets échantillonnés** de l'itinéraire (jusqu'à 1,7 km
   d'écart sur les longs trajets ruraux) : un événement de sévérité 0,9 à 0 m était lu à 120 m, donc ignoré ;
2. la déviation était choisie sur le seul critère « risque global ≥ 0,12 plus faible », même si l'alternative
   traversait le danger déclencheur ;
3. les détours n'étaient cherchés qu'autour du **milieu du trajet** : pour 21 des 27 segments de la ligne 1, une
   route de contournement existait mais n'était jamais trouvée.

### Décision

Les seuils ne changent pas : déviation si le risque du trajet le plus rapide est **≥ 0,42** et si une alternative est
**au moins 0,12 plus sûre** (`REROUTE_MIN_RISK`, `REROUTE_MIN_GAIN`).

1. **Mesure :** distance vraie entre chaque danger et la ligne complète de l'itinéraire, en PostGIS
   (`ST_Distance` en `geography`, mètres). Rayon d'exposition inchangé : 105 m.
2. **Éligibilité d'une alternative :** elle doit rester à **plus de 105 m de chaque danger déclencheur**.
   Dangers déclencheurs = chaque danger du trajet le plus rapide qui, **à lui seul**, porte ce trajet à ≥ 0,42 ;
   si aucun ne le fait seul (seul leur cumul dépasse 0,42), tous les dangers du trajet. Définition indépendante de
   l'ordre des dangers. Si le risque vient uniquement des scores M2 des segments (aucun danger ponctuel), la règle
   précédente s'applique.
3. **Recherche :** en plus des détours autour du milieu du trajet, M3 cherche des détours autour de chaque danger
   déclencheur (points de passage perpendiculaires à 0,5 / 1 / 2 / 3 km de chaque côté ; dangers à moins de 500 m
   regroupés ; au plus 6 groupes, les plus dangereux d'abord).
4. **Aucune alternative éligible :** si le trajet est ≥ 0,42 et qu'aucune alternative éligible n'est 0,12 plus sûre,
   pas de déviation, mais une alerte au conducteur `driver.route.warning`
   « Danger sur l'itinéraire — aucune alternative sûre », avec la liste des dangers (type, position, risque,
   distance au trajet).
5. **Textes d'alerte cohérents :** « X danger(s) sur le trajet initial, Y sur l'alternative ; risque A % → B % »,
   les deux comptes étant mesurés de la même façon. Les alertes portent `logic_version = "m3-v2"`.

### Conséquences mesurées (23/10, base de démo)

- Avec les données de démo (24 dangers, dont 10 à 12 le long de RN11), **les 4 lignes passent en avertissement** :
  aucune alternative n'évite tous les dangers déclencheurs. L'ancienne déviation de la ligne 2 passait elle-même à
  0 m de 12 dangers ; elle est conservée en base, marquée `superseded` / `logic_version = "m3-v1"`.
- Test d'isolement (code réel, OSRM et PostGIS réels, seul un danger de 0,9 sur OSM-125567491) : déviation
  par un itinéraire de 28,2 km qui passe à 1 397 m du danger (risque 0,774 → 0,193). La recherche « milieu seul »
  ne trouvait aucune alternative.
- Temps de réponse de `/routing/route` sur les 4 lignes : 0,85–6,1 s avant, 0,17–4,5 s après (la recherche
  autour des dangers multiplie les candidats par ~6, compensé par la correction de la requête de segments).

### Limites connues

- Sur un corridor unique (ex. RN11 entre Bizerte et Menzel Bourguiba), plusieurs dangers successifs rendent toute
  alternative inéligible : le conducteur reçoit un avertissement, pas une déviation. C'est voulu : on ne propose
  pas d'itinéraire « plus sûr » qui traverse le même danger.
- Au plus 6 groupes de dangers explorés par requête.
- Le risque M2 des segments reste calculé sur une version échantillonnée de l'itinéraire (≤ 300 points).
