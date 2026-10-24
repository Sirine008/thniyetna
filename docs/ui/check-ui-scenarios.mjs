// Scenarios of check-ui.mjs, one group per redesigned screen.
export default async function scenarios({ scenario, check, focusVisible, BASE, USERS, PASSWORDS, lib, apiAs, SHEET, OUT_DIR, fs }) {
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
      fs.writeFileSync(`${OUT_DIR}/sheet-print.pdf.bin`, pdf);
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
}
