'use strict';
// Optional real-browser suite. Use externally installed Playwright; no site dependencies.
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright');
const { KEY } = require('../docs/assets/checklist.js');
const root = path.resolve(__dirname, '../docs');
let server, browser, base;
before(async () => {
  server = http.createServer(async (req, res) => {
    try {
      const relative = decodeURIComponent(new URL(req.url, 'http://localhost').pathname).replace(/^\/cmail\//, '');
      const file = path.resolve(root, relative === '' ? 'index.html' : relative);
      if (!file.startsWith(root + path.sep)) throw new Error('Outside docs');
      const types = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.md': 'text/plain' };
      res.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream');
      res.end(await fs.readFile(file));
    } catch { res.statusCode = 404; res.end('Not found'); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${server.address().port}/cmail/`;
  browser = await chromium.launch({ headless: true, ...(process.env.CHROME_BIN ? { executablePath: process.env.CHROME_BIN } : {}) });
});
after(async () => {
  if (browser) await browser.close();
  if (server) await new Promise(resolve => server.close(resolve));
});
async function context(options = {}) {
  const ctx = await browser.newContext(options);
  await ctx.route('**/*', route => route.request().url().startsWith(base) ? route.continue() : route.abort());
  return ctx;
}
async function pageFor(ctx, filename = 'setup.html') {
  const page = await ctx.newPage();
  const errors = [], responses = [], failures = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => responses.push({ url: response.url(), status: response.status() }));
  page.on('requestfailed', request => failures.push(request.url()));
  await page.goto(base + filename);
  return { page, errors, responses, failures };
}

test('native labels, keyboard Space toggles, progress and persistence across reload', async () => {
  const ctx = await context();
  try {
    const { page, errors } = await pageFor(ctx);
    const input = page.getByRole('checkbox', { name: 'I checked prerequisites and migration impact', exact: true });
    await input.focus(); await page.keyboard.press('Space');
    assert.equal(await input.isChecked(), true);
    assert.match(await page.locator('#progress-count').innerText(), /1 of 14/);
    await page.reload(); assert.equal(await input.isChecked(), true);
    await input.focus(); await page.keyboard.press('Space');
    assert.equal(await input.isChecked(), false);
    await page.locator('label[for="step-readiness"]').click();
    assert.equal(await input.isChecked(), true);
    assert.deepEqual(errors, []);
    const stored = await page.evaluate(key => JSON.parse(localStorage.getItem(key)), KEY);
    assert.equal(Object.keys(stored.steps).length, 14);
    assert.ok(Object.values(stored.steps).every(value => typeof value === 'boolean'));
  } finally { await ctx.close(); }
});
test('keyboard reset removes only own key and remains reset after reload', async () => {
  const ctx = await context();
  try {
    const { page } = await pageFor(ctx);
    await page.getByRole('checkbox').first().check();
    await page.evaluate(() => localStorage.setItem('unrelated', 'retained'));
    await page.getByRole('button', { name: 'Reset progress' }).focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#setup-progress').evaluate(e => e.value), 0);
    assert.equal(await page.evaluate(key => localStorage.getItem(key), KEY), null);
    assert.equal(await page.evaluate(() => localStorage.getItem('unrelated')), 'retained');
    await page.reload(); assert.equal(await page.getByRole('checkbox').first().isChecked(), false);
  } finally { await ctx.close(); }
});
test('no-JS guide has usable native checkboxes and hides enhancement controls', async () => {
  const ctx = await context({ javaScriptEnabled: false });
  try {
    const { page } = await pageFor(ctx);
    assert.equal(await page.getByRole('checkbox').count(), 14);
    const input = page.getByRole('checkbox').first();
    await input.focus(); await page.keyboard.press('Space'); assert.equal(await input.isChecked(), true);
    await page.keyboard.press('Space'); assert.equal(await input.isChecked(), false);
    assert.equal(await page.locator('#progress-panel').isVisible(), false);
    assert.match(await page.locator('noscript').innerText(), /JavaScript is off/);
    assert.equal(await page.locator('#delivery').isVisible(), true);
  } finally { await ctx.close(); }
});
test('malformed, primitive, wrong-type and unknown stored state does not break controls', async () => {
  const ctx = await context();
  try {
    const { page, errors } = await pageFor(ctx);
    for (const raw of ['{', 'null', '[]', '42', '{"version":1,"steps":{"readiness":"yes"}}', '{"version":1,"steps":{"unknown":true}}']) {
      await page.evaluate(({ key, raw }) => localStorage.setItem(key, raw), { key: KEY, raw });
      await page.reload(); assert.equal(await page.getByRole('checkbox').first().isChecked(), false);
      assert.match(await page.locator('#storage-notice').innerText(), /invalid/);
      await page.getByRole('checkbox').first().check();
      assert.equal(await page.locator('#setup-progress').evaluate(e => e.value), 1);
    }
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});
test('blocked localStorage getter degrades to session toggles and reset', async () => {
  const ctx = await context();
  try {
    await ctx.addInitScript(() => Object.defineProperty(window, 'localStorage', { get() { throw new Error('Storage denied'); } }));
    const { page, errors } = await pageFor(ctx);
    assert.match(await page.locator('#storage-notice').innerText(), /unavailable/);
    await page.getByRole('checkbox').first().check();
    assert.equal(await page.locator('#setup-progress').evaluate(e => e.value), 1);
    await page.getByRole('button', { name: 'Reset progress' }).click();
    assert.equal(await page.getByRole('checkbox').first().isChecked(), false);
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});
test('write/remove errors are visible and do not disable native controls', async () => {
  const ctx = await context();
  try {
    await ctx.addInitScript(() => {
      Storage.prototype.setItem = () => { throw new Error('Quota'); };
      Storage.prototype.removeItem = () => { throw new Error('Denied'); };
    });
    const { page, errors } = await pageFor(ctx);
    await page.getByRole('checkbox').first().check();
    assert.match(await page.locator('#storage-notice').innerText(), /could not be saved/);
    await page.getByRole('button', { name: 'Reset progress' }).click();
    assert.equal(await page.getByRole('checkbox').first().isChecked(), false);
    assert.match(await page.locator('#storage-notice').innerText(), /may return after reload/);
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});
test('all checked steps retain visible safety details; completion is not verification', async () => {
  const ctx = await context();
  try {
    const { page } = await pageFor(ctx);
    for (const input of await page.getByRole('checkbox').all()) await input.check();
    assert.equal(await page.locator('#setup-progress').evaluate(e => e.value), 14);
    assert.match(await page.locator('#progress-count').innerText(), /not automatic provider verification/);
    assert.equal(await page.locator('#delegation aside').isVisible(), true);
  } finally { await ctx.close(); }
});
for (const width of [375, 768, 1280]) {
  test(`offline static site at ${width}px has no overflow or broken assets`, async () => {
    const ctx = await context({ viewport: { width, height: 900 } });
    try {
      for (const filename of ['index.html', 'setup.html']) {
        const { page, errors, responses, failures } = await pageFor(ctx, filename);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        assert.equal(await page.locator('h1').isVisible(), true);
        assert.equal(await page.evaluate(() => getComputedStyle(document.body).color), 'rgb(0, 0, 0)');
        await page.reload();
        const assets = ['assets/styles.css', ...(filename === 'setup.html' ? ['assets/checklist.js'] : [])];
        for (const asset of assets) {
          assert.ok(responses.some(response => response.url === base + asset && response.status === 200), asset);
        }
        assert.ok(responses.length >= 2);
        assert.ok(responses.every(response => response.status === 200));
        assert.deepEqual(failures, []);
        if (process.env.SCREENSHOT_DIR) {
          await fs.mkdir(process.env.SCREENSHOT_DIR, { recursive: true });
          await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, `${filename}-${width}.png`), fullPage: true });
        }
        assert.deepEqual(errors, []);
        await page.close();
      }
    } finally { await ctx.close(); }
  });
}
