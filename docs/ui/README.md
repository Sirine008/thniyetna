# Citizen page screenshots

Taken on 24/10/2026 with `check-citizen.mjs`: headless Microsoft Edge 155 driven by `playwright-core` 1.64.1, against
the running stack (`http://localhost:8081`), logged in as `demo.citizen1` (password read from
`data/demo/demo_accounts.json`, never printed). Desktop 1280 × 800 and mobile 390 × 844 (touch, ×2).
The script runs 28 checks (shared link through the login, « Ma position » first, Arabic autocomplete and keyboard,
automatic check, swap, map-click rule, drag of B, the three validation messages, warning card, mobile stacking,
44 px targets, no horizontal scroll) and rewrites the screenshots below.

```powershell
# once, outside the repository (no change to frontend/package.json)
mkdir $env:TEMP\uicheck; cd $env:TEMP\uicheck; npm init -y; npm install playwright-core@1.64.1
copy <repo>\docs\ui\check-citizen.mjs .; node check-citizen.mjs <repo>
```

| File | Content |
|---|---|
| `citizen-desktop-empty.png` | Empty page: no start, shortcuts fill « Arrivée » |
| `citizen-desktop-start-suggestions.png` | « Départ » focused: « Ma position », then « Centre de Bizerte » |
| `citizen-desktop-autocomplete.png` | « Arrivée » search in Arabic (منزل بورقيبة) |
| `citizen-desktop-shared-reroute.png` | Shared link Bizerte → Menzel Bourguiba: « Alternative plus sûre recommandée » |
| `citizen-desktop-warning.png` | Bizerte → Mateur: « Danger sur l’itinéraire — aucune alternative sûre » |
| `citizen-desktop-same-points.png` | « Le départ et l’arrivée sont identiques » |
| `citizen-desktop-out-of-zone.png` | « Destination hors de la zone couverte (gouvernorat de Bizerte) » |
| `citizen-mobile-empty.png` | 390 px: stacked fields, map below |
| `citizen-mobile-autocomplete.png` | 390 px: « hopital » suggestions |
| `citizen-mobile-result.png` | 390 px: Centre de Bizerte → Hôpital Militaire, « Trajet vérifié » |
