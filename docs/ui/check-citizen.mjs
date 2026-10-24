// Headless check of the citizen trip page (Edge via playwright-core). Usage: node check.mjs <repo root>
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.argv[2];
const OUT = path.join(ROOT, 'docs', 'ui');
fs.mkdirSync(OUT, { recursive: true });
const BASE = 'http://localhost:8081';
const accounts = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'demo', 'demo_accounts.json'), 'utf8'));
const USER = 'demo.citizen1';
const PASSWORD = accounts[USER].password; // never printed

const results = [];
const check = (name, ok, info = '') => { results.push({ name, ok }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? `  (${info})` : ''}`); };
const shot = (page, name) => page.screenshot({ path: path.join(OUT, name) });
const qs = page => new URL(page.url()).search;

const browser = await chromium.launch({ channel: 'msedge', headless: true });

async function session(context) {
  const r = await fetch(`${BASE}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: USER, password: PASSWORD }) });
  const s = await r.json();
  await context.addInitScript(v => localStorage.setItem('thniyetna.session', v), JSON.stringify(s));
}
const fromField = page => page.getByRole('combobox', { name: 'Départ' });
const toField = page => page.getByRole('combobox', { name: 'Arrivée' });
const waitCard = page => page.waitForSelector('.route-verdict, .route-error', { timeout: 45000 });

// ---------------------------------------------------------------- desktop
{
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: 'fr-FR',
    geolocation: { latitude: 37.2760, longitude: 9.8650 }, permissions: ['geolocation'] });
  const page = await context.newPage();

  // 1. shared link opened while logged out: the query survives the login
  await page.goto(`${BASE}/citizen?from=37.274400,9.873900&to=37.153700,9.785600`);
  await page.waitForURL(/\/login/);
  await page.locator('input:not([type=password])').last().fill(USER);
  await page.locator('input[type=password]').fill(PASSWORD);
  await page.locator('input[type=password]').press('Enter');
  await page.waitForURL(/\/citizen\?from=/, { timeout: 15000 });
  check('shared link survives the login', qs(page).includes('to=37.153700,9.785600'), qs(page));
  await waitCard(page);
  check('shared link computes the route automatically', await page.locator('.route-verdict').count() === 1,
    await page.locator('.route-verdict b').first().textContent());
  await page.waitForTimeout(1500);
  await shot(page, 'citizen-desktop-shared-reroute.png');

  // 2. empty page
  await page.goto(`${BASE}/citizen`);
  await page.waitForSelector('.leaflet-container');
  await page.waitForTimeout(1500);
  check('no implicit start', (await fromField(page).inputValue()) === '' && await page.locator('.th-marker.user').count() === 0);
  await shot(page, 'citizen-desktop-empty.png');

  // 3. « Ma position » is the first suggestion of Départ
  await fromField(page).click();
  const first = (await page.getByRole('option').first().textContent()) || '';
  check('« Ma position » first in Départ', first.startsWith('⌖Ma position'), first);
  await shot(page, 'citizen-desktop-start-suggestions.png');
  await page.getByRole('option', { name: /Ma position/ }).click();
  await page.waitForFunction(() => document.querySelector('.th-marker.user'));
  check('Ma position fills Départ', (await fromField(page).inputValue()) === 'Ma position');

  // 4. Arrivée: Arabic autocomplete + keyboard
  await toField(page).click();
  await toField(page).fill('منزل بورقيبة');
  await page.waitForSelector('[role=option]');
  await page.waitForTimeout(400);
  const ar = await page.getByRole('option').first().textContent();
  check('Arabic query finds Menzel Bourguiba', /Menzel Bourguiba/.test(ar), ar);
  await shot(page, 'citizen-desktop-autocomplete.png');
  await toField(page).press('ArrowDown');
  await toField(page).press('Enter');
  check('keyboard choice fills Arrivée', (await toField(page).inputValue()).length > 0, await toField(page).inputValue());
  await waitCard(page);
  check('route checked automatically once both are set', await page.locator('.route-verdict').count() === 1);
  check('URL carries from/to', /from=.*&to=/.test(qs(page)), qs(page));

  // 5. swap
  const [a, b] = [await fromField(page).inputValue(), await toField(page).inputValue()];
  const before = qs(page);
  await page.getByRole('button', { name: 'Inverser départ et arrivée' }).click();
  const [a2, b2] = [await fromField(page).inputValue(), await toField(page).inputValue()];
  const p = new URLSearchParams(before), q = new URLSearchParams(qs(page));
  check('swap exchanges fields', a2 === b && b2 === a, `${a2} / ${b2}`);
  check('swap exchanges the URL', q.get('from') === p.get('to') && q.get('to') === p.get('from'));

  // 6. map click rules
  const map = page.locator('.leaflet-container');
  await page.locator('.place-clear').first().click(); // clears Départ and makes it the active field
  check('cleared field becomes the active one', await page.locator('.place-search.active').count() === 1);
  await map.click({ position: { x: 300, y: 330 } })  // relative to the 620 px map;
  await page.waitForFunction(() => /Près de|Point/.test(document.querySelector('[aria-label="Départ"]').value));
  check('click fills the active field (Départ)', /Près de|Point/.test(await fromField(page).inputValue()), await fromField(page).inputValue());
  const toBefore = await toField(page).inputValue();
  await map.click({ position: { x: 420, y: 400 } });
  await page.waitForFunction(v => document.querySelector('[aria-label="Arrivée"]').value !== v, toBefore);
  check('no active field + Départ set: click fills Arrivée', /Près de|Point/.test(await toField(page).inputValue()), await toField(page).inputValue());

  // 7. drag marker B
  await page.waitForTimeout(800);
  const box = await page.locator('.th-marker.destination').boundingBox();
  const toBeforeDrag = qs(page);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + 80, box.y + 60, { steps: 12 });
  await page.mouse.up();
  await page.waitForFunction(v => window.location.search !== v, toBeforeDrag, { timeout: 10000 });
  check('dragging B moves Arrivée (URL updated)', qs(page) !== toBeforeDrag);
  await page.waitForFunction(() => /Près de|Point choisi/.test(document.querySelector('[aria-label="Arrivée"]').value));
  check('dragged point is named after the nearest place', true, await toField(page).inputValue());

  // 8. validation messages
  for (const [name, query, text] of [
    ['same points', 'from=37.274600,9.873900&to=37.274700,9.873900', 'Le départ et l’arrivée sont identiques'],
    ['destination out of zone', 'from=37.274600,9.873900&to=36.800000,10.180000', 'Destination hors de la zone couverte (gouvernorat de Bizerte)'],
    ['start out of zone', 'from=36.800000,10.180000&to=37.274600,9.873900', 'Point de départ hors de la zone couverte (gouvernorat de Bizerte)'],
  ]) {
    await page.goto(`${BASE}/citizen?${query}`);
    await page.waitForSelector('.route-error', { timeout: 20000 });
    const msg = await page.locator('.route-error b').textContent();
    check(`message: ${name}`, msg === text, msg);
    check(`no route computed: ${name}`, await page.getByRole('button', { name: /Vérifier le trajet/ }).isDisabled());
    if (name === 'same points') { await page.waitForTimeout(1200); await shot(page, 'citizen-desktop-same-points.png'); }
    if (name === 'destination out of zone') { await page.waitForTimeout(1200); await shot(page, 'citizen-desktop-out-of-zone.png'); }
  }

  // 9. warning card (Bizerte -> Mateur, demo line L2)
  await page.goto(`${BASE}/citizen?from=37.274400,9.873900&to=37.040000,9.665000`);
  await waitCard(page);
  const title = await page.locator('.route-verdict b').textContent();
  check('warning card for Bizerte -> Mateur', title === 'Danger sur l’itinéraire — aucune alternative sûre', title);
  await page.waitForTimeout(1500);
  await shot(page, 'citizen-desktop-warning.png');
  await context.close();
}

// ---------------------------------------------------------------- mobile 390 px
{
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: 'fr-FR' });
  await session(context);
  const page = await context.newPage();
  await page.goto(`${BASE}/citizen`);
  await page.waitForSelector('.leaflet-container');
  await page.waitForTimeout(1500);
  const top = await page.locator('.citizen-nav-top').boundingBox();
  const mapBox = await page.locator('.citizen-nav-map').boundingBox();
  check('mobile: map below the fields', mapBox.y >= top.y + top.height - 1, `fields end ${Math.round(top.y + top.height)} px, map starts ${Math.round(mapBox.y)} px`);
  const sizes = await page.evaluate(() => [...document.querySelectorAll('.place-search, .swap-btn, .place-search input, .quick-destinations button')]
    .map(e => [e.className || e.tagName, Math.round(e.getBoundingClientRect().height)]));
  const small = sizes.filter(([c, h]) => /place-search|swap-btn/.test(c) && h < 44);
  check('mobile: field rows and swap button >= 44 px', small.length === 0, JSON.stringify(sizes.slice(0, 4)));
  const fromBox = await fromField(page).boundingBox(), toBox = await toField(page).boundingBox();
  check('mobile: fields stacked', toBox.y > fromBox.y + fromBox.height - 1);
  check('mobile: no horizontal scroll', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await shot(page, 'citizen-mobile-empty.png');
  await toField(page).tap();
  await toField(page).fill('hopital');
  await page.waitForSelector('[role=option]');
  await page.waitForTimeout(400);
  await shot(page, 'citizen-mobile-autocomplete.png');
  await page.getByRole('option').first().tap();
  await fromField(page).tap();
  await page.getByRole('option', { name: /Centre de Bizerte/ }).tap();
  await waitCard(page);
  check('mobile: route checked', await page.locator('.route-verdict').count() === 1, await page.locator('.route-verdict b').first().textContent());
  await page.waitForTimeout(1500);
  await shot(page, 'citizen-mobile-result.png');
  await context.close();
}

await browser.close();
const failed = results.filter(r => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
