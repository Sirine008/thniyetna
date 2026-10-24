# UI: design system and headless checks

## Design system (frontend/src)

| Where | What |
|---|---|
| `styles/tokens.css` | Colour, type, spacing (4/8/12/16/24/32), radius (4–6 px), border, shadow and z-index tokens. Petrol accent; green / yellow / orange / red only for risk levels, priorities and states. AA contrast tested by `lib/tokens.test.js`. |
| `ui/` | Button, Badge (risk, priority, report state, alert type, demo), Card, KPI tile, DataTable (sort, pagination, stacked rows + sort select on mobile), Toolbar, Tabs, SidePanel, Modal, ConfirmModal, Toast, EmptyState, Spinner / Skeleton, Field, Timeline, MapLegend, ImageBoxes. |
| `lib/labels.js` | The one French label for every technical value (defect classes, report states, alert topics, roles, road classes, M2 factors as « augmente / diminue le risque », known API errors). |
| `lib/format.js` | 2-decimal scores, percentages, m / km, durations, dates in Africa/Tunis (« 23 oct. 2026, 18:44 »). |
| `/design` | Reference page of the tokens and components (supervisor roles). |

Rules: one accent colour; colour always paired with text or an icon; borders over shadows (shadows only for
popovers, dropdowns and modals); Lucide line icons, no emoji; logical CSS properties only (RTL-ready); no number on
screen that does not come from the API.

## Headless checks

Both scripts drive the installed Microsoft Edge with `playwright-core` against the running stack
(`http://localhost:8081`), at 1440 × 900 and 390 × 844 (touch). Logins use `data/demo/demo_accounts.json` and
`BOOTSTRAP_PASSWORD` from `.env` (read, never printed). Screenshots and PDFs are written next to the scripts
(`docs/ui/after/`) and are not committed.

| Script | Scope |
|---|---|
| `check-ui.mjs` (+ `check-ui-scenarios.mjs`) | Every role and screen, grouped: `design auth layout equipment sheet transport driver citizen assistant accounts`. **Read-only on the database:** every write is intercepted, recorded and answered locally, and the checks assert the exact request body the UI sends (same as before the redesign). `next-best` is answered by the side-effect-free `/routing/route`. The intervention sheet and the assistant replay one real recorded response (`sheet.json`, `ask.json` from `record-*.mjs`, next to the script) because the LLM takes 30–100 s. |
| `check-citizen.mjs` | Départ / Arrivée regression of the citizen route page (28 checks). |

```powershell
# once, outside the repository (no change to frontend/package.json)
mkdir $env:TEMP\uicheck; cd $env:TEMP\uicheck; npm init -y; npm install playwright-core@1.64.1
copy <repo>\docs\ui\check-*.mjs .
node check-ui.mjs <repo>                    # all groups (about 5 min)
node check-ui.mjs <repo> equipment,sheet    # some groups
node check-citizen.mjs <repo>
```

`AUDIT.md`: the pre-redesign audit (« before » screenshots in `docs/ui/before/`, not committed).
The PNGs already tracked in this folder are the citizen screenshots of 24/10/2026 (before the redesign).
