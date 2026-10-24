# UI audit before the redesign (24/10/2026)

"Before" screenshots: `docs/ui/before/<role>-<screen>-<desktop|mobile>.png` (1440 and 390 px, 46 files, not committed),
taken read-only (writes blocked) from the running stack. Accounts: `demo.citizen1`, `demo.driver2`, `demo.inspection`,
`equipment.supervisor`, `transport.supervisor`.

| Role | Screens | Main problems |
|---|---|---|
| Public | Accueil, connexion, inscription | Gradient and glow background, icon tiles, slogan « La route intelligente, sûre et connectée », technical footer (« API + PostGIS + OSRM ») |
| Citoyen | Itinéraire, signalement, suivi | Slogan « Voyagez avec une route vérifiée », 8–9 px text, pastel cards with 20–28 px radius, emoji-like glyphs (◎ ⌖ ＋), technical copy (« le backend publie un événement SSE »), status list without history |
| Conducteur | Trajet, alertes | Dark theme with glows and gradient button; « SSE » shown as a metric; small text; alert times in 12-hour format |
| Véhicule d’inspection | — | No web screen: the account lands on the public home page |
| Superviseur Équipement | Signalements, détections, priorités, inspections, assistant, comptes, fiche d’intervention | Signalements: 21 records in one long list with an inline form per row, no filter / sort / pagination; raw values (`road_damage`, `alligator crack`); times « 9:04 PM »; no detail view (photo, history); detections without the image box; priorities without a map; tabs only (no layout) |
| Superviseur Transport | Réseau à risque, affectations, lignes & flotte, assistant, comptes | Same layout issues; tables without sorting; raw vehicle types (`bus`); no map of the risky network |

Shared: no design tokens (colours hard-coded in two stylesheets), no shared components (buttons, badges, tables, messages),
colour used decoratively (teal everywhere), percentages without French spacing, dates in the device time zone.
