import { expect, Page, test } from '@playwright/test';

// What a visitor sees and does (MYLA-635): every page renders without an
// error, the editors run Myla in the browser, an exercise can be solved,
// search finds things, deep links work.

function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    // the download page looks for the CI's manifest, which a local build lacks
    if (m.type() === 'error' && !/downloads\/manifest\.json|status of 404/.test(m.text())) errors.push(m.text());
  });
  return errors;
}

const PAGES: [string, RegExp][] = [
  ['', /compiles itself/],
  ['quickstart', /Hello, Universe/],
  ['download', /Get Myla/],
  ['docs', /The Myla language/],
  ['docs/types', /^Types$/],
  ['docs/concurrency', /Concurrency/],
  ['reference', /The standard library/],
  ['reference/builtins', /Builtins/],
  ['reference/vector', /std\.vector/],
  ['reference/http', /std\.http/],
  ['learn', /Grand Line/],
  ['learn/dont-panic', /Don't Panic/],
  ['learn/dont-panic/hello-galaxy', /Hello, Galaxy/],
  ['learn/profile', /journey/],
  ['playground', /Playground/],
  ['no/such/page', /404/],
];

for (const [path, heading] of PAGES) {
  test(`/${path} renders`, async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto(path);
    await expect(page.locator('h1, .code').filter({ hasText: heading }).first()).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test('the hero program runs in the browser and prints 42', async ({ page }) => {
  await page.goto('');
  const editor = page.locator('myla-editor').first();
  await editor.getByRole('button', { name: 'Run' }).click();
  await expect(editor.locator('.output')).toContainText('Life, the universe and everything: 42', { timeout: 30_000 });
  await expect(editor.locator('.output')).toContainText('Output as expected');
});

test("a docs page's example runs and matches its expected output", async ({ page }) => {
  await page.goto('docs/structs-enums-and-match');
  const editor = page.locator('app-doc-content .myla-example').filter({ has: page.getByRole('button', { name: 'Run' }) }).first();
  await editor.scrollIntoViewIfNeeded();
  await editor.getByRole('button', { name: 'Run' }).click();
  await expect(editor.locator('.output')).toContainText('Output as expected', { timeout: 30_000 });
});

test('an exercise is solved, earns XP, and stays solved', async ({ page }) => {
  await page.goto('learn/dont-panic/hello-galaxy');
  const content = page.locator('myla-editor .cm-content');
  await content.click();
  await page.keyboard.press('ControlOrMeta+a');
  // in one piece: typed key by key, the editor would close the brackets too
  await page.keyboard.insertText('fun main() {\n    print("Hello, Galaxy!")\n}\n');
  await page.getByRole('button', { name: /Check/ }).click();
  await expect(page.locator('.verdict.ok')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('.toast').first()).toContainText('+10 XP');
  await expect(page.locator('.toast').filter({ hasText: "Don't Panic" })).toBeVisible();
  await page.reload();
  await expect(page.locator('.chip.good')).toContainText('solved');
  await expect(page.locator('app-header .xp')).toContainText('Lv 1');
});

test('a wrong answer is not accepted', async ({ page }) => {
  await page.goto('learn/dont-panic/the-answer');
  await page.getByRole('button', { name: /Check/ }).click();
  await expect(page.locator('.verdict:not(.ok)')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('.verdict .detail')).toContainText('The answer is 13');
});

test('the search finds a method and goes to it', async ({ page }) => {
  await page.goto('');
  await page.keyboard.press('ControlOrMeta+k');
  await page.getByRole('searchbox', { name: 'Search' }).fill('str.split');
  await expect(page.locator('.results li').first()).toContainText('split');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/reference\/str/);
});

test('the theme switches and is kept', async ({ page }) => {
  await page.goto('');
  const before = await page.locator('html').getAttribute('data-theme');
  await page.getByRole('button', { name: /theme/ }).click();
  const after = await page.locator('html').getAttribute('data-theme');
  expect(after).not.toBe(before);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', after!);
});

test('the playground shares a program in its link', async ({ page }) => {
  await page.goto('playground#code=' + Buffer.from('fun main() {\n    print(6 * 7)\n}\n').toString('base64url'));
  await page.locator('myla-editor').getByRole('button', { name: 'Run' }).click();
  await expect(page.locator('myla-editor .output')).toContainText('42', { timeout: 30_000 });
});

test('a phone sees no sideways scrolling', async ({ browser }) => {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  for (const path of ['', 'docs/types', 'reference/vector', 'learn', 'learn/dont-panic/hello-galaxy']) {
    await page.goto(path);
    await page.locator('h1').first().waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
  await page.close();
});
