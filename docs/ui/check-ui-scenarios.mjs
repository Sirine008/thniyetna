// Scenarios of check-ui.mjs, one group per redesigned screen.
export default async function scenarios({ scenario, check, focusVisible, BASE, USERS, PASSWORDS }) {
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
}
