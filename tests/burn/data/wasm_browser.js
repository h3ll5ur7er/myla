// wasm_browser.js — the playground page (tools/wasm/page.html) in Chromium through
// Playwright (tests/burn/test_wasm.py): `node wasm_browser.js <dir>` serves the
// directory, runs the page's example, checks a type error, and runs a
// runtime error and an endless recursion through the API; prints JSON.

const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const root = process.argv[2];
const types = { '.html': 'text/html', '.mjs': 'text/javascript', '.wasm': 'application/wasm' };
const server = http.createServer((req, res) => {
  const f = path.join(root, req.url === '/' ? 'page.html' : req.url.split('?')[0]);
  if (!fs.existsSync(f)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'application/octet-stream' });
  res.end(fs.readFileSync(f));
}).listen(0, async () => {
  const port = server.address().port;
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(`http://127.0.0.1:${port}/`);
  await page.waitForFunction(() => window.mylaReady === true, null, { timeout: 60000 });
  await page.click('#run');
  await page.waitForFunction(() => window.lastRun, null, { timeout: 60000 });
  const run = await page.evaluate(() => ({ stdout: window.lastRun.stdout, exitCode: window.lastRun.exitCode }));
  await page.fill('#source', 'fun main() {\n    let x: int = "a"\n    print(x)\n}\n');
  await page.click('#check');
  await page.waitForFunction(() => window.lastCheck, null, { timeout: 60000 });
  const check = await page.evaluate(() => window.lastCheck);
  const shown = await page.textContent('#diagnostics');
  // a runtime error and an infinite recursion, from the page's own module
  const more = await page.evaluate(async () => {
    const { loadMyla } = await import('./myla.mjs');
    const m = await loadMyla(fetch('play.wasm'));
    const a = await m.run('fun main() {\n    let xs = [1]\n    print(xs[2])\n}\n');
    const b = await m.run('fun f(n: int) -> int {\n    return f(n + 1) + 1\n}\n\nfun main() {\n    print(f(0))\n}\n');
    return { a: [a.stderr, a.exitCode], b: [b.stderr, b.exitCode] };
  });
  console.log(JSON.stringify({ run, check, shown, more, errors }, null, 1));
  await browser.close();
  server.close();
});
