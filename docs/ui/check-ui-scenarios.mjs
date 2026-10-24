// Scenarios of check-ui.mjs, one group per redesigned screen.
export default async function scenarios({ scenario, check, focusVisible, BASE }) {
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
}
