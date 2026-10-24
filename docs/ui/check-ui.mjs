// Headless UI checks for every role (Edge via playwright-core), 1440 and 390 px, with screenshots.
//   node check-ui.mjs <repo> [group,group...]     groups: design auth layout equipment sheet transport driver citizen assistant accounts
// Read-only on the database: every write (POST/PATCH except login, route computation and place search) is
// intercepted, recorded and answered locally, so the checks assert the exact request the UI sends.
// Passwords: data/demo/demo_accounts.json and BOOTSTRAP_PASSWORD (.env) for the supervisors; never printed.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.argv[2];
const ONLY = (process.argv[3] || '').split(',').filter(Boolean);
const OUT = path.join(ROOT, 'docs', 'ui', 'after');
fs.mkdirSync(OUT, { recursive: true });
export const BASE = 'http://localhost:8081';
const demo = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/demo/demo_accounts.json'), 'utf8'));
const env = fs.readFileSync(path.join(ROOT, '.env'), 'utf8');
const BOOT = (env.match(/^BOOTSTRAP_PASSWORD=(.*)$/m) || [])[1]?.trim().replace(/^["']|["']$/g, '');
const SHEET = path.join(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1')), 'sheet.json');
const sheet = fs.existsSync(SHEET) ? JSON.parse(fs.readFileSync(SHEET, 'utf8')) : null;
export const USERS = { citizen: 'demo.citizen1', driver: 'demo.driver2', equipment: 'equipment.supervisor', transport: 'transport.supervisor', inspection: 'demo.inspection' };
const password = user => demo[user]?.password ?? BOOT;

const results = [];
export const check = (name, ok, info = '') => { results.push({ name, ok: !!ok }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? `  (${info})` : ''}`); };

async function sessionFor(user) {
  const r = await fetch(`${BASE}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: user, password: password(user) }) });
  if (!r.ok) throw new Error(`login ${user}: HTTP ${r.status}`);
  return r.text();
}

/** Records API calls; answers writes locally. `replies` maps a URL regex source to a JSON body for writes. */
async function instrument(page, replies = {}) {
  const calls = [];
  await page.route('**/api/**', async route => {
    const req = route.request(), url = new URL(req.url()), method = req.method();
    const entry = { method, path: url.pathname.replace(/^\/api/, ''), query: url.search, body: req.postData() };
    calls.push(entry);
    if (url.pathname.includes('/routing/driver/next-best')) {
      // same computation without the driver-alert write (alert counters stay unchanged)
      const r = await fetch(`${BASE}/api/routing/route`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: req.postData() });
      return route.fulfill({ status: r.status, contentType: 'application/json', body: await r.text() });
    }
    if (url.pathname.includes('/assistant/intervention/') && sheet) {
      await new Promise(r => setTimeout(r, 1500));
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(sheet.body) });
    }
    const readOnly = method === 'GET' || /\/auth\/login|\/routing\/route$|\/routing\/places/.test(url.pathname);
    if (readOnly) return route.continue();
    const key = Object.keys(replies).find(k => new RegExp(k).test(entry.path));
    const body = key ? replies[key](entry) : { status: 'ok' };
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  return calls;
}

const VIEWS = { desktop: { viewport: { width: 1440, height: 900 } }, mobile: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true } };
let browser;

/** Runs `steps(page, ctx)` for a role at both widths. ctx: { view, shot, calls, noScroll } */
export async function scenario(group, role, steps, { views = ['desktop', 'mobile'], replies = {}, geolocation } = {}) {
  if (ONLY.length && !ONLY.includes(group)) return;
  for (const view of views) {
    const context = await browser.newContext({ ...VIEWS[view], locale: 'fr-FR', timezoneId: 'Europe/Paris', ...(geolocation ? { geolocation, permissions: ['geolocation'] } : {}) });
    if (role) { const s = await sessionFor(USERS[role] || role); await context.addInitScript(v => localStorage.setItem('thniyetna.session', v), s); }
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const calls = await instrument(page, replies);
    const shot = async name => { await page.waitForTimeout(900); await page.screenshot({ path: path.join(OUT, `${group}-${name}-${view}.png`), fullPage: view === 'desktop' }); };
    const noScroll = async label => {
      const w = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
      check(`${group} ${label} ${view}: no horizontal scroll`, w[0] <= w[1], `${w[0]} / ${w[1]}`);
    };
    try { await steps(page, { view, shot, calls, noScroll }); }
    catch (e) { check(`${group} ${view}: scenario ran`, false, e.message.split('\n')[0]); }
    check(`${group} ${view}: no JavaScript error`, errors.length === 0, errors[0]);
    await context.close();
  }
}

/** Visible focus: Tab to the first focusable element and check an outline is drawn. */
export async function focusVisible(page, label) {
  await page.keyboard.press('Tab');
  const style = await page.evaluate(() => { const el = document.activeElement; const cs = el && getComputedStyle(el); return el && el !== document.body ? `${cs.outlineStyle} ${cs.outlineWidth}` : 'none'; });
  check(`${label}: focus is visible`, /solid|auto/.test(style) && !/ 0px/.test(style), style);
}

browser = await chromium.launch({ channel: 'msedge', headless: true });
const groups = await import('./check-ui-scenarios.mjs');
await groups.default({ scenario, check, focusVisible, BASE, USERS, PASSWORDS: { citizen: password(USERS.citizen) } });
await browser.close();
const failed = results.filter(r => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed${failed.length ? ` — FAILED: ${failed.map(f => f.name).join(' | ')}` : ''}`);
process.exit(failed.length ? 1 : 0);
