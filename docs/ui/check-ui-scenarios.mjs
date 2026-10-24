// Scenarios of check-ui.mjs, one group per redesigned screen.
export default async function scenarios({ scenario, check, focusVisible, BASE, USERS, PASSWORDS, lib, apiAs, SHEET, OUT_DIR, fs, ASK }) {
  // ------------------------------------------------------------ design system reference
  await scenario('design', 'equipment', async (page, { view, shot, noScroll }) => {
    await page.goto(`${BASE}/design`);
    await page.waitForSelector('text=Système de conception THNIYETNA');
    check(`design ${view}: all sections render`, (await page.locator('.card').count()) >= 14);
    await noScroll('page');
    await page.getByRole('button', { name: 'Ouvrir le panneau' }).click();
    check(`design ${view}: side panel opens with focus inside`, await page.evaluate(() => !!document.activeElement.closest('.side-panel')));
    await page.keyboard.press('Escape');
    check(`design ${view}: Escape closes the panel and returns focus`, (await page.locator('.side-panel').count()) === 0
      && await page.evaluate(() => document.activeElement.textContent.includes('Ouvrir le panneau')));
    if (view === 'desktop') await page.locator('.table th .sort-btn').first().click();
    else await page.locator('.table-mobile-sort select').selectOption('name:asc');
    check(`design ${view}: sortable column`, (await page.locator('.table th[aria-sort="ascending"]').count()) === 1
      && (await page.locator('.table tbody tr').first().textContent()).includes('Exemple de ligne A'));
    if (view === 'mobile') check('design mobile: table rows are stacked', await page.evaluate(() => getComputedStyle(document.querySelector('.table-stack td')).display === 'grid'));
    await shot('page');
  });

  // ------------------------------------------------------------ 1. entry page, login, citizen sign-up
  await scenario('auth', null, async (page, { view, shot, calls, noScroll }) => {
    await page.goto(`${BASE}/`);
    const hrefs = await page.locator('.role-link').evaluateAll(links => links.map(a => a.getAttribute('href')));
    check(`auth ${view}: same 4 login links as before`, JSON.stringify(hrefs) === JSON.stringify([
      '/login?role=citizen&next=%2Fcitizen', '/login?role=bus_driver&next=%2Fdriver',
      '/login?role=equipment_supervisor&next=%2Fministry%2Fequipment', '/login?role=transport_supervisor&next=%2Fministry%2Ftransport']), hrefs.join(' '));
    check(`auth ${view}: no slogan`, !(await page.content()).includes('intelligente'));
    await noScroll('home'); await focusVisible(page, `auth home ${view}`); await shot('home');

    await page.goto(`${BASE}/login?role=bus_driver&next=%2Fdriver`);
    check(`auth ${view}: identifier pre-filled for the role`, (await page.getByLabel('Identifiant').inputValue()) === 'driver.srtb');
    check(`auth ${view}: no sign-up for staff roles`, (await page.getByRole('button', { name: 'Créer un compte' }).count()) === 0);
    await page.getByLabel('Identifiant').fill('demo.citizen1');
    await page.getByLabel('Mot de passe').fill('mauvais-mot-de-passe');
    await page.getByRole('button', { name: 'Se connecter' }).click();
    await page.waitForSelector('.notice-error');
    check(`auth ${view}: wrong password shows a French error`, (await page.locator('.notice-error').textContent()).includes('Identifiant ou mot de passe incorrect.'));
    await shot('login-error');

    await page.goto(`${BASE}/login?role=citizen&next=%2Fcitizen%2Fclaims`);
    await noScroll('login'); await shot('login');
    await page.getByRole('button', { name: 'Créer un compte' }).click();
    check(`auth ${view}: sign-up shows the display-name field`, await page.getByLabel('Nom affiché').isVisible());
    await shot('signup');
    await page.getByLabel('Nom affiché').fill('Test Vérif');
    await page.getByLabel('Identifiant').fill('verif.ui');
    await page.getByLabel('Mot de passe').fill('motdepasse-123');
    await page.getByRole('button', { name: 'Créer le compte' }).click();
    await page.waitForURL(/\/citizen\/claims/);
    const reg = calls.find(c => c.path === '/auth/register');
    check(`auth ${view}: sign-up sends the same request`, reg && reg.method === 'POST' && JSON.stringify(JSON.parse(reg.body)) === JSON.stringify({ username: 'verif.ui', password: 'motdepasse-123', display_name: 'Test Vérif' }), reg?.body);
  }, { replies: { '^/auth/register$': () => ({ access_token: 'x.e30.x', token_type: 'bearer', role: 'citizen', display_name: 'Test Vérif' }) } });

  await scenario('auth', null, async (page, { view }) => {
    await page.goto(`${BASE}/login?role=bus_driver&next=%2Fdriver`);
    await page.getByLabel('Identifiant').fill(USERS.citizen);
    await page.getByLabel('Mot de passe').fill(PASSWORDS.citizen);
    await page.getByRole('button', { name: 'Se connecter' }).click();
    await page.waitForSelector('.notice-error');
    check(`auth ${view}: role mismatch is refused`, (await page.locator('.notice-error').textContent()).includes('Ce compte appartient au rôle'));
    await page.goto(`${BASE}/login?role=citizen&next=%2Fcitizen%2Fclaims`);
    await page.getByLabel('Identifiant').fill(USERS.citizen);
    await page.getByLabel('Mot de passe').fill(PASSWORDS.citizen);
    await page.getByRole('button', { name: 'Se connecter' }).click();
    await page.waitForURL(/\/citizen\/claims/);
    check(`auth ${view}: real login lands on the requested page`, true);
  });

  // ------------------------------------------------------------ 2. layouts
  const LOAD = {
    equipment: ['GET /platform/dashboard/equipment', 'GET /platform/complaints', 'GET /perception/events?limit=100', 'GET /perception/inspections?limit=100', 'GET /platform/map', 'GET /prediction/model', 'GET /auth/staff'],
    transport: ['GET /platform/dashboard/transport', 'GET /routing/official-routes', 'GET /platform/vehicles', 'GET /routing/assignments', 'GET /platform/map', 'GET /prediction/governorates', 'GET /prediction/model', 'GET /auth/staff'],
  };
  for (const ministry of ['equipment', 'transport']) {
    await scenario('layout', ministry, async (page, { view, shot, calls, noScroll }) => {
      await page.goto(`${BASE}/ministry/${ministry}`);
      await page.waitForSelector('.sup-shell');
      await page.waitForLoadState('networkidle');
      const loaded = [...new Set(calls.filter(c => c.method === 'GET').map(c => `${c.method} ${c.path}${c.query}`))].filter(c => !c.includes('/realtime/'));
      check(`layout ${ministry} ${view}: same requests on load as before`, JSON.stringify([...loaded].sort()) === JSON.stringify([...LOAD[ministry]].sort()), loaded.join(', '));
      check(`layout ${ministry} ${view}: top bar shows user and role`, (await page.locator('.sup-user-name').textContent()).includes('Superviseur') || view === 'mobile');
      await noScroll('shell');
      if (view === 'mobile') {
        check(`layout ${ministry} mobile: sidebar hidden until the menu is opened`, !(await page.locator('.sup-sidebar').isVisible()));
        await page.getByRole('button', { name: 'Ouvrir le menu' }).click();
        await page.waitForTimeout(250);
        check(`layout ${ministry} mobile: menu opens the sidebar`, await page.locator('.sup-sidebar').isVisible());
        await shot('menu');
        await page.keyboard.press('Escape');
        await page.waitForTimeout(250);
        check(`layout ${ministry} mobile: Escape closes the menu`, !(await page.locator('.sup-sidebar').isVisible()));
        await page.getByRole('button', { name: 'Ouvrir le menu' }).click();
      }
      const links = page.locator('.sup-nav-link');
      const second = links.nth(1);
      const label = (await second.textContent()).replace(/\d+$/, '');
      await second.click();
      await page.waitForURL(/vue=/);
      check(`layout ${ministry} ${view}: sidebar link opens the section`, (await page.locator('.sup-nav-link[aria-current="page"]').textContent()).startsWith(label) && (await page.locator('h1').first().textContent()) === label, label);
      const requestsAfter = calls.filter(c => c.method === 'GET' && !c.path.includes('realtime')).length;
      check(`layout ${ministry} ${view}: switching section does not refetch (as before)`, requestsAfter === loaded.length, `${requestsAfter}`);
      await shot('shell');
      await page.locator('.sup-user .btn').click();
      await page.waitForURL(`${BASE}/`);
      check(`layout ${ministry} ${view}: logout clears the session`, await page.evaluate(() => localStorage.getItem('thniyetna.session') === null));
    });
  }
  for (const [role, base, expected] of [['citizen', '/citizen', ['/citizen', '/citizen/map', '/citizen/report', '/citizen/claims']], ['driver', '/driver', ['/driver', '/driver/map', '/driver/alerts']]]) {
    await scenario('layout', role, async (page, { view }) => {
      await page.goto(`${BASE}${base}/claims`.replace('/driver/claims', '/driver/alerts'));
      await page.waitForSelector('.bottom-nav');
      const hrefs = await page.locator('.bottom-nav a').evaluateAll(as => as.map(a => a.getAttribute('href')));
      check(`layout ${role} ${view}: bottom navigation keeps the same destinations`, JSON.stringify(hrefs) === JSON.stringify(expected), hrefs.join(' '));
      const heights = await page.locator('.bottom-nav a').evaluateAll(as => as.map(a => a.getBoundingClientRect().height));
      check(`layout ${role} ${view}: bottom navigation targets >= 44 px`, heights.every(h => h >= 44), heights.join(','));
    }, { views: ['mobile'] });
  }

  // ------------------------------------------------------------ 3. equipment supervisor
  const segLib = await lib('segments');
  const dash = await apiAs('equipment', '/platform/dashboard/equipment');
  const complaints = await apiAs('equipment', '/platform/complaints');
  const events = await apiAs('equipment', '/perception/events?limit=100');
  const map = await (await fetch(`${BASE}/api/platform/map`)).json();
  const tableRows = page => page.locator('.table tbody tr').count();
  const countText = async page => { await page.waitForSelector('.table tbody tr, .empty-state'); return Number((await page.locator('.toolbar-count').textContent()).match(/\d+/)[0]); };

  await scenario('equipment', 'equipment', async (page, { view, shot, calls, noScroll }) => {
    await page.goto(`${BASE}/ministry/equipment`);
    await page.waitForSelector('.kpi');
    const kpis = await page.locator('.kpi .kpi-value').allTextContents();
    check(`equipment home ${view}: KPI values are the dashboard API counts`, JSON.stringify(kpis.map(Number)) === JSON.stringify([dash.open_complaints, dash.unvalidated_events, dash.events_24h, dash.active_inspections]), kpis.join(','));
    await noScroll('home'); await focusVisible(page, `equipment home ${view}`); await shot('home');
    await page.locator('.kpi').first().click();
    await page.waitForURL(/statut=a-traiter/);
    await page.waitForSelector('.toolbar-count');
    check(`equipment ${view}: open-reports tile opens the filtered list with the same count`, (await countText(page)) === dash.open_complaints, `${await countText(page)} / ${dash.open_complaints}`);

    // signalements: all by default (as before), side panel, history, status change request
    await page.goto(`${BASE}/ministry/equipment?vue=signalements`);
    await page.waitForSelector('.toolbar-count');
    check(`equipment reports ${view}: all reports listed by default`, (await countText(page)) === complaints.length, `${await countText(page)} / ${complaints.length}`);
    check(`equipment reports ${view}: paginated (20 rows max)`, (await tableRows(page)) === Math.min(20, complaints.length));
    await noScroll('reports'); await shot('reports');
    const target = complaints.find(c => c.status === 'open') || complaints[0];
    await page.goto(`${BASE}/ministry/equipment?vue=signalements&signalement=${target.id}`);
    await page.waitForSelector('.side-panel .timeline, .side-panel .notice-error', { timeout: 15000 });
    check(`equipment reports ${view}: panel loads the history (GET history)`, calls.some(c => c.path === `/platform/complaints/${target.id}/history`));
    check(`equipment reports ${view}: panel shows the mini-map`, await page.waitForSelector('.side-panel .leaflet-container', { timeout: 10000 }).then(() => true, () => false));
    const select = page.locator('.side-panel select');
    const shown = await select.inputValue();
    check(`equipment reports ${view}: default target status as before`, shown === (target.status === 'open' ? 'under_review' : target.status), shown);
    await page.locator('.side-panel textarea').fill('Vérification UI');
    await shot('report-panel');
    await page.getByRole('button', { name: 'Enregistrer le statut' }).click();
    await page.waitForTimeout(800);
    const patch = calls.find(c => c.method === 'PATCH');
    check(`equipment reports ${view}: same PATCH as before`, patch && patch.path === `/platform/complaints/${target.id}/status` && patch.body === JSON.stringify({ status: shown, note: 'Vérification UI' }), patch?.body);
    check(`equipment reports ${view}: success toast`, (await page.locator('.toast').count()) >= 1);
    await page.keyboard.press('Escape');

    // détections: pending by default, photo with box, validate request
    await page.goto(`${BASE}/ministry/equipment?vue=detections`);
    await page.waitForSelector('.toolbar-count');
    const pending = events.filter(e => !e.validated);
    check(`equipment detections ${view}: only detections to validate by default (as before)`, (await countText(page)) === pending.length, `${await countText(page)} / ${pending.length}`);
    await noScroll('detections'); await shot('detections');
    const withObs = await apiAs('equipment', '/perception/observations?limit=500');
    const ev = pending.find(e => withObs.some(o => o.event_id === e.id && o.bbox_xyxy)) || pending[0];
    if (ev) {
      await page.goto(`${BASE}/ministry/equipment?vue=detections&detection=${ev.id}`);
      await page.waitForSelector('.side-panel');
      await page.waitForSelector('.side-panel img', { timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(1200);
      const boxes = await page.locator('.side-panel .image-boxes svg rect').count();
      const expected = withObs.filter(o => o.event_id === ev.id && o.bbox_xyxy).length;
      check(`equipment detections ${view}: photo with the model box`, expected ? boxes >= 1 : true, `${boxes / 2} box(es), ${expected} observation(s)`);
      check(`equipment detections ${view}: French class and percentages`, /Confiance du modèle\d+\s%/.test(await page.locator('.side-panel').textContent()));
      await shot('detection-panel');
      await page.locator('.side-panel-foot').getByRole('button', { name: 'Valider la détection' }).click();
      await page.waitForTimeout(800);
      const v = calls.find(c => c.method === 'PATCH' && c.path.startsWith('/perception/events/'));
      check(`equipment detections ${view}: same validate request`, v && v.path === `/perception/events/${ev.id}/validate` && !v.body, v?.path);
    }

    // priorités: same worklist as before, table + map in sync
    await page.goto(`${BASE}/ministry/equipment?vue=priorites`);
    await page.waitForSelector('.toolbar-count');
    const queue = segLib.maintenanceQueue(map.segments);
    check(`equipment priorities ${view}: same worklist size as before`, (await countText(page)) === queue.length, `${await countText(page)} / ${queue.length}`);
    await page.waitForSelector('.leaflet-overlay-pane path', { timeout: 15000 });
    check(`equipment priorities ${view}: segments drawn on the map`, (await page.locator('.leaflet-overlay-pane path').count()) >= Math.min(queue.length, 1));
    if (queue.length) {
      await page.locator('.table tbody tr').first().click();
      await page.waitForURL(/segment=/);
      check(`equipment priorities ${view}: row click selects the segment`, (await page.locator('.table tbody tr.is-selected').count()) === 1);
    }
    await noScroll('priorities'); await shot('priorities');
    await page.goto(`${BASE}/ministry/equipment?vue=inspections`);
    await page.waitForSelector('.empty-state, .table');
    await noScroll('inspections'); await shot('inspections');
  }, { replies: { 'status$': e => ({ id: e.path.split('/')[3], status: JSON.parse(e.body).status }), 'validate$': () => ({ status: 'validated' }) } });

  // ------------------------------------------------------------ 4. intervention sheet (recorded real response replayed)
  await scenario('sheet', 'equipment', async (page, { view, shot, calls, noScroll }) => {
    const code = SHEET?.segment_code;
    await page.goto(`${BASE}/ministry/equipment?vue=priorites&q=${encodeURIComponent(code)}`);
    await page.waitForSelector('.table tbody tr');
    const opener = page.getByRole('button', { name: /Fiche d’intervention/ }).first();
    await opener.click();
    await page.waitForSelector('.generating');
    check(`sheet ${view}: generating state with elapsed time while the sheet is produced`, /s écoulées/.test(await page.locator('.generating').textContent()));
    await shot('generating');
    await page.waitForSelector('.sheet-section', { timeout: 20000 });
    const post = calls.find(c => c.path.startsWith('/assistant/intervention/'));
    check(`sheet ${view}: same request (POST /assistant/intervention/{code})`, post && post.method === 'POST' && post.path === `/assistant/intervention/${code}`, post?.path);
    check(`sheet ${view}: every section of the response is shown`, (await page.locator('.sheet-section').count()) === SHEET.body.sections.length + (SHEET.body.sources.length ? 1 : 0));
    const text = await page.locator('.sheet-page').textContent();
    check(`sheet ${view}: French labels, no raw class or status`, !/alligator_crack|road_damage|statut open|\bprimary\b/.test(text) && text.includes('Faïençage'));
    check(`sheet ${view}: Tunis time (17:44 UTC shown as 18:44)`, text.includes('23 oct. 2026, 18:44'));
    check(`sheet ${view}: rounded values (score 0,42, severity 73 %)`, text.includes('0,42') && /73\s%/.test(text));
    check(`sheet ${view}: uncited advice is flagged`, (await page.locator('.uncited').count()) === SHEET.body.sections.filter(s => s.uncited).length);
    check(`sheet ${view}: no demo banner for real data`, (await page.locator('.sheet-page .demo-banner').count()) === 0);
    await noScroll('sheet');
    await shot('sheet');
    await page.emulateMedia({ media: 'print' });
    check(`sheet ${view}: print shows only the sheet`, !(await page.locator('#root').isVisible()) && await page.locator('.sheet-page').isVisible() && !(await page.getByRole('button', { name: 'Imprimer' }).isVisible()));
    if (view === 'desktop') {
      await page.screenshot({ path: `${OUT_DIR}/sheet-print-desktop.png`, fullPage: true });
      const pdf = await page.pdf({ format: 'A4', printBackground: false, preferCSSPageSize: true });
      fs.writeFileSync(`${OUT_DIR}/sheet-print.pdf`, pdf);
      check('sheet desktop: A4 PDF generated from the print stylesheet', pdf.length > 10000, `${Math.round(pdf.length / 1024)} KB`);
    }
    await page.emulateMedia({ media: 'screen' });
    await page.keyboard.press('Escape');
    check(`sheet ${view}: Escape closes the sheet`, (await page.locator('.sheet-wrap').count()) === 0);

    // demo data: banner
    const demoBody = JSON.parse(JSON.stringify(SHEET.body));
    demoBody.facts.events[0].demo = true;
    await page.route('**/api/assistant/intervention/**', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(demoBody) }));
    await opener.click();
    await page.waitForSelector('.sheet-section');
    check(`sheet ${view}: demo banner when a row is demo data`, (await page.locator('.sheet-page .demo-banner').count()) === 1);
    await page.keyboard.press('Escape');
  });

  // ------------------------------------------------------------ 5. transport supervisor
  {
    const tdash = await apiAs('transport', '/platform/dashboard/transport');
    const govs = await apiAs('transport', '/prediction/governorates');
    const routesRef = await apiAs('transport', '/routing/official-routes');
    const vehiclesRef = await apiAs('transport', '/platform/vehicles');
    const staffRef = await apiAs('transport', '/auth/staff');
    const tmap = await (await fetch(`${BASE}/api/platform/map`)).json();
    const seg = await lib('segments');
    const count = async page => { await page.waitForSelector('.table tbody tr, .empty-state'); return page.locator('.table tbody tr').count(); };
    await scenario('transport', 'transport', async (page, { view, shot, calls, noScroll }) => {
      await page.goto(`${BASE}/ministry/transport`);
      await page.waitForSelector('.kpi');
      const kpis = (await page.locator('.kpi .kpi-value').allTextContents()).map(Number);
      check(`transport home ${view}: KPI values are the dashboard API counts`, JSON.stringify(kpis) === JSON.stringify([tdash.active_routes, tdash.active_buses, tdash.assignments, tdash.high_risk_updates]), kpis.join(','));
      await noScroll('home'); await shot('home');

      await page.goto(`${BASE}/ministry/transport?vue=reseau`);
      await page.waitForSelector('.card');
      const forecasts = seg.dayForecasts(govs);
      const firstTable = page.locator('.card').first().locator('.table tbody tr');
      check(`transport network ${view}: one row per governorate for the next day`, (await firstTable.count()) === forecasts.length, `${await firstTable.count()} / ${forecasts.length}`);
      const shown = seg.riskySegments(tmap.segments).length ? seg.riskySegments(tmap.segments) : seg.exposureTop(tmap.segments);
      const segRows = await page.locator('.card').nth(1).locator('.table tbody tr').count();
      check(`transport network ${view}: same watched segments as before`, segRows === Math.min(15, shown.length), `${segRows} / ${shown.length}`);
      if (shown.length) await page.waitForSelector('.leaflet-overlay-pane path', { timeout: 15000 }).then(() => check(`transport network ${view}: map drawn`, true), () => check(`transport network ${view}: map drawn`, false));
      await noScroll('network'); await shot('network');

      await page.goto(`${BASE}/ministry/transport?vue=lignes`);
      await count(page);
      check(`transport fleet ${view}: all lines and vehicles listed`, (await page.locator('.card').first().locator('.table tbody tr').count()) === Math.min(20, routesRef.length)
        && (await page.locator('.card').nth(1).locator('.table tbody tr').count()) === Math.min(20, vehiclesRef.length));
      await noScroll('fleet'); await shot('fleet');
      await page.getByRole('button', { name: 'Ajouter un véhicule' }).first().click();
      await page.getByLabel('Code').fill('UI-CHECK-BUS');
      await page.getByLabel('Libellé').fill('Contrôle UI');
      await shot('vehicle-form');
      await page.getByRole('button', { name: 'Enregistrer le véhicule' }).click();
      await page.waitForTimeout(800);
      const veh = calls.find(c => c.method === 'POST' && c.path === '/platform/vehicles');
      check(`transport fleet ${view}: same vehicle request`, veh && veh.body === JSON.stringify({ vehicle_code: 'UI-CHECK-BUS', vehicle_type: 'bus', owner_org: 'SRTB', label: 'Contrôle UI' }), veh?.body);
      check(`transport fleet ${view}: modal closes after success`, (await page.locator('.modal').count()) === 0);
      await page.getByRole('button', { name: 'Créer une ligne' }).first().click();
      await page.getByLabel('Code de la ligne').fill('UI-CHECK-L');
      await page.getByLabel('Nom').fill('Contrôle UI');
      const lat = page.getByLabel('Latitude'), lon = page.getByLabel('Longitude');
      await lat.nth(0).fill('37.2744'); await lon.nth(0).fill('9.8739'); await lat.nth(1).fill('37.2540'); await lon.nth(1).fill('9.8770');
      await page.getByRole('button', { name: 'Calculer et enregistrer la ligne' }).click();
      await page.waitForTimeout(2500);
      const plan = calls.find(c => c.path === '/routing/route');
      const saved = calls.find(c => c.path === '/routing/official-routes' && c.method === 'POST');
      check(`transport fleet ${view}: line computed with the same OSRM request`, plan && JSON.stringify(JSON.parse(plan.body)) === JSON.stringify({ vehicle_id: 'transport-planning', current_lat: 37.2744, current_lon: 9.8739, destination_lat: 37.254, destination_lon: 9.877, alternatives: 0 }), plan?.body);
      const savedBody = saved && JSON.parse(saved.body);
      check(`transport fleet ${view}: line saved with the same payload`, savedBody && savedBody.route_code === 'UI-CHECK-L' && savedBody.name === 'Contrôle UI' && savedBody.owner_org === 'SRTB' && savedBody.active === true && savedBody.coordinates.length > 1, saved ? `${savedBody.coordinates.length} points` : 'no request');

      await page.goto(`${BASE}/ministry/transport?vue=affectations`);
      await count(page);
      const firstRoute = routesRef.find(r => r.active)?.route_code || '', firstBus = vehiclesRef.find(v => v.vehicle_type === 'bus' && v.active)?.vehicle_code || '', firstDriver = staffRef.find(a => a.role === 'bus_driver' && a.active)?.username || '';
      const selects = page.locator('form select');
      check(`transport assignments ${view}: same pre-selection as before`, (await selects.nth(0).inputValue()) === firstRoute && (await selects.nth(1).inputValue()) === firstBus && (await selects.nth(2).inputValue()) === firstDriver);
      await noScroll('assignments'); await shot('assignments');
      await page.getByRole('button', { name: 'Confirmer l’affectation' }).click();
      await page.waitForTimeout(800);
      const asg = calls.find(c => c.method === 'POST' && c.path === '/routing/assignments');
      check(`transport assignments ${view}: same assignment request`, asg && asg.body === JSON.stringify({ route_code: firstRoute, vehicle_code: firstBus, driver_username: firstDriver }), asg?.body);
    }, { replies: { '^/platform/vehicles$': e => ({ ...JSON.parse(e.body), active: true }), '^/routing/official-routes$': () => ({ id: 'x', route_code: 'UI-CHECK-L', name: 'Contrôle UI' }), '^/routing/assignments$': () => ({ status: 'assigned', id: 'x' }) } });
  }

  // ------------------------------------------------------------ 6. driver (mobile first)
  {
    const mine = await apiAs('driver', '/routing/driver/me');
    const alertsRef = await apiAs('driver', '/platform/alerts');
    const dest = (() => { const c = mine[0]?.geometry?.coordinates; if (!c?.length) return null; const line = Array.isArray(c[0]?.[0]) ? c[c.length - 1] : c; const last = line[line.length - 1]; return [last[1], last[0]]; })();
    const GEO = { latitude: 37.2744, longitude: 9.8739 };
    const body = dest && { vehicle_id: mine[0].vehicle_code, current_lat: GEO.latitude, current_lon: GEO.longitude, destination_lat: dest[0], destination_lon: dest[1], alternatives: 3 };
    const expected = body && await (await fetch(`${BASE}/api/routing/route`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json();
    const rs = await lib('routeState');
    await scenario('driver', 'driver', async (page, { view, shot, calls, noScroll }) => {
      await page.goto(`${BASE}/driver`);
      await page.waitForSelector('.drive-banner', { timeout: 45000 });
      const nb = calls.filter(c => c.path === '/routing/driver/next-best');
      check(`driver ${view}: same next-best request as before`, nb.length === 1 && nb[0].body === JSON.stringify(body), nb[0]?.body);
      const kind = rs.routeState(expected).kind;
      check(`driver ${view}: banner state matches the route decision (${kind})`, (await page.locator(`.drive-banner.is-${kind}`).count()) === 1);
      check(`driver ${view}: every hazard listed`, (await page.locator('.drive-hazards li').count()) === (expected.hazards?.length || 0));
      check(`driver ${view}: line name shown`, (await page.locator('.drive-line h1').textContent()) === mine[0].name);
      await noScroll('trip'); await shot('trip');
      await page.getByRole('button', { name: 'Vérifier et recalculer' }).click();
      await page.waitForFunction(() => !document.querySelector('[aria-busy="true"]'));
      check(`driver ${view}: recalculate sends the same request again`, calls.filter(c => c.path === '/routing/driver/next-best').length === 2);
      await page.goto(`${BASE}/driver/alerts`);
      await page.waitForSelector('.alert-feed, .empty-state');
      check(`driver alerts ${view}: one entry per alert of the API`, (await page.locator('.alert-entry').count()) === alertsRef.length, `${alertsRef.length}`);
      check(`driver alerts ${view}: superseded alerts marked`, (await page.locator('.alert-entry.is-superseded').count()) === alertsRef.filter(a => a.payload?.superseded).length);
      check(`driver alerts ${view}: « Confirmée n× » shown`, (await page.locator('.alert-entry .badge', { hasText: 'Confirmée' }).count()) === alertsRef.filter(a => a.payload?.confirmations > 1).length);
      await noScroll('alerts'); await shot('alerts');
    }, { geolocation: GEO });
  }

  // ------------------------------------------------------------ 7. citizen (route page logic: docs/ui/check-citizen.mjs)
  {
    const GEO = { latitude: 37.2700, longitude: 9.8600 };
    const mineRef = await apiAs('citizen', '/platform/complaints/mine');
    await scenario('citizen', 'citizen', async (page, { view, shot, calls, noScroll }) => {
      await page.goto(`${BASE}/citizen`);
      await page.waitForSelector('.nav-welcome');
      check(`citizen route ${view}: functional title, no slogan`, (await page.locator('.nav-welcome h1').textContent()) === 'Vérifier un itinéraire' && !(await page.content()).includes('Voyagez avec'));
      check(`citizen route ${view}: no emoji in the place suggestions`, await page.locator('.trip-box').evaluate(el => !/\p{Extended_Pictographic}/u.test(el.textContent)));
      await noScroll('route'); await shot('route');
      await page.goto(`${BASE}/citizen?from=37.274400,9.873900&to=37.040000,9.665000`);
      await page.waitForSelector('.route-verdict', { timeout: 45000 });
      await shot('route-warning');

      await page.goto(`${BASE}/citizen/report`);
      await page.waitForSelector('form');
      await page.waitForFunction(() => document.body.textContent.includes('position GPS'));
      await page.getByLabel('Inondation').check();
      await page.getByLabel('Description').fill('Chaussée inondée — contrôle UI');
      await page.locator('input[type=file]').setInputFiles({ name: 'photo.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64') });
      await noScroll('report'); await shot('report');
      await page.getByRole('button', { name: 'Envoyer le signalement' }).click();
      await page.waitForURL(/\/citizen$/, { timeout: 10000 });
      const upload = calls.find(c => c.method === 'POST' && c.path === '/media/image');
      const claim = calls.find(c => c.method === 'POST' && c.path === '/platform/complaints');
      check(`citizen report ${view}: photo uploaded first (POST /media/image)`, !!upload && calls.indexOf(upload) < calls.indexOf(claim));
      check(`citizen report ${view}: same complaint request`, claim && claim.body === JSON.stringify({ description: 'Chaussée inondée — contrôle UI', latitude: GEO.latitude, longitude: GEO.longitude, category: 'flooding', image_url: '/media/files/ui-check.png', image_storage_key: 'ui-check' }), claim?.body);
      check(`citizen report ${view}: back to the route page after success (as before)`, page.url().endsWith('/citizen'));

      await page.goto(`${BASE}/citizen/claims`);
      await page.waitForSelector('.claim-feed, .empty-state');
      check(`citizen claims ${view}: one entry per report of the API`, (await page.locator('.claim-entry').count()) === mineRef.length, `${mineRef.length}`);
      if (mineRef.length) {
        await page.locator('.claim-progress summary').first().click();
        check(`citizen claims ${view}: status timeline`, (await page.locator('.claim-progress[open] .timeline-item').count()) >= 2);
      }
      await noScroll('claims'); await shot('claims');
    }, { geolocation: GEO, replies: { '^/media/image$': () => ({ media_uri: '/media/files/ui-check.png', storage_key: 'ui-check' }), '^/platform/complaints$': e => ({ id: 'x', status: 'open', ...JSON.parse(e.body) }) } });
  }

  // ------------------------------------------------------------ 8. assistant (recorded real answer replayed)
  if (ASK) {
    const status = await apiAs('equipment', '/assistant/status');
    const asked = [];   // requests answered by the replay (registered after the recorder, so it sees them first)
    const replay = body => async route => { const r = route.request(); asked.push({ method: r.method(), body: r.postData() }); await new Promise(res => setTimeout(res, 1500)); await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }); };
    await scenario('assistant', 'equipment', async (page, { view, shot, calls, noScroll }) => {
      await page.route('**/api/assistant/ask', replay(ASK.body));
      await page.goto(`${BASE}/ministry/equipment?vue=assistant`);
      await page.waitForSelector('.chat');
      await page.waitForFunction(() => !document.querySelector('.chat .card-head [role=status]')?.textContent.includes('Vérification'));
      const line = await page.locator('.chat .card-head [role=status]').textContent();
      check(`assistant ${view}: status from GET /assistant/status`, status.ollama?.reachable ? line.includes(`${status.documents}`) && line.includes(`${status.chunks}`) : line.includes('indisponible'), line);
      await noScroll('empty'); await shot('empty');
      await page.getByLabel('Votre question').fill(ASK.question);
      await page.getByRole('button', { name: 'Envoyer la question' }).click();
      await page.waitForSelector('.generating');
      check(`assistant ${view}: generating state while the answer is produced`, /s écoulées/.test(await page.locator('.generating').textContent()));
      await shot('generating');
      await page.waitForSelector('.chat-answer');
      const ask = asked[asked.length - 1];
      check(`assistant ${view}: same request (POST /assistant/ask {question})`, ask && ask.method === 'POST' && ask.body === JSON.stringify({ question: ASK.question }), ask?.body);
      const cited = /\[\d/.test(ASK.body.answer);
      check(`assistant ${view}: answer shown with its sources`, (await page.locator('.chat-answer .source-item').count()) === (ASK.body.sources?.length || 0));
      check(`assistant ${view}: no-citation message only when the answer cites nothing`, (await page.locator('.chat-answer .uncited').count()) === (cited ? 0 : 1));
      if (cited) {
        await page.locator('.citation-link').first().click();
        await page.waitForTimeout(400);
        check(`assistant ${view}: a citation opens and focuses its source`, await page.evaluate(() => document.activeElement?.classList.contains('source-item')));
      }
      check(`assistant ${view}: history kept for the session (same storage key)`, await page.evaluate(() => JSON.parse(sessionStorage.getItem('thniyetna.assistant.equipment') || '[]').length === 1));
      await noScroll('answer'); await shot('answer');
      const uncited = { ...ASK.body, answer: ASK.body.answer.replace(/\[\d+(?:\s*,\s*\d+)*\]/g, '') };
      await page.unroute('**/api/assistant/ask');
      await page.route('**/api/assistant/ask', replay(uncited));
      await page.getByLabel('Votre question').fill('Question sans citation dans la réponse');
      await page.getByRole('button', { name: 'Envoyer la question' }).click();
      await page.waitForFunction(() => document.querySelectorAll('.chat-answer').length === 2, null, { timeout: 15000 });
      check(`assistant ${view}: clear message when an answer has no citation`, (await page.locator('.chat-exchange').last().locator('.uncited').count()) === 1);
    });
  }
}
