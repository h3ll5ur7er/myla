# Website

The Myla website (D208, [[MYLA-159]]): an Angular app in `website/`, static, deployed to GitHub Pages by CI on every push to master. Its docs, reference and course are generated from the repository, and every code example on it runs the real toolchain in the browser.

[TOC]

## What it is made of

| Part | Where | What |
| --- | --- | --- |
| The app | `website/src/app` | Angular 22: standalone components, signals, zoneless change detection, a lazy route per page. `core/` holds the services (content, toolchain, progress, search, theme), `editor/` the editor, `content/` the renderer of converted pages, `shell/` the header, footer, search palette and toasts, `pages/` the pages |
| The design | `website/src/styles.scss` | Tokens on `:root` (dark first, `[data-theme="light"]` for light), three self-hosted typefaces (Space Grotesk, Inter, JetBrains Mono), the prose of converted pages |
| The docs | `docs/Language*.md`, `docs/Getting-started.md` | Converted at build time by `website/scripts/content.mjs` (below): the wiki is the single source |
| The reference | `lib/std/*.my` | `tools/doc` ([[MYLA-632]]) gives each module's public API with its doc comments and `#test` cases, from the self-hosted parser (the language server's outline); each module's page joins it with the module's wiki page |
| The course | `learn/` | Chapters of exercises ([[MYLA-634]], `learn/README.md`) |
| The toolchain | `selfhost/play_main.my`, `tools/wasm/*.mjs` | `play.wasm` ([[MYLA-158]]), the checker and interpreter built for wasm32-wasi, run in a Web Worker |
| The samples | `website/src/app/pages/home/samples/*.my` | The landing page's programs, imported as text (`angular.json`'s loader for `.my`), each ending with its expected output |

## The build

`npm run build` (or `npm run build:pages` for GitHub Pages' base path `/myla/`) runs, in `website/`:

1. `scripts/prepare.mjs`, with the toolchain of `scripts/bootstrap.sh` (`build/myla`, or `$MYLA`):
   - `play.wasm` built from `selfhost/play_main.my`, and `tools/wasm/{myla,wasi,mem_fs}.mjs` and `src/worker/myla.worker.mjs` copied, into `public/play/`;
   - `tools/doc/main.my` built natively and run over the standard library (but `rt`, `platform*` and `slice`, which are internal): `build/website/api.json`;
   - `scripts/content.mjs` writing `public/content/`: `site.json` (the navigation), `search.json` (the search index), `docs/<slug>.json`, `reference/<module>.json`, `quickstart.json`, `playground.json` (the repository's single-file examples) and `learn.json`.
2. `ng build`, into `dist/`.
3. `scripts/postbuild.mjs`: `dist/404.html`, a copy of the app, so GitHub Pages answers a deep link (`/myla/docs/types`) with the app, which routes it.

`public/play/` and `public/content/` are generated and ignored by git. `npm start` prepares without rebuilding `play.wasm` when there is one, then serves the app with `ng serve`.

### Converting a wiki page

`scripts/lib/markdown.mjs` turns a page into `{ title, html, examples, toc }`:

- The first `#` heading is the title. The `##` and `###` headings get GitHub's anchors and make the table of contents.
- `[[…]]` links become links to the site's routes: [[Language]] is `/docs`, a `Language/…` page `/docs/<name>`, [[Language/Standard-library]] `/reference`, a module's page `/reference/<module>`, [[Getting-started]] `/quickstart`. Other pages, tasks and files link to the repository on GitHub. Links inside code are left alone.
- A `myla` block becomes `<div class="myla-example" data-i="N">` and the N-th example: its source, its expected output (its trailing `// output:` comment) and its kind. The kinds are `run` (it has a `main`), `check`, `fragment` (`myla fragment`, shown only) and `error` (`myla error`, meant to fail the checker).
- Tables are wrapped to scroll on their own on a narrow screen. Genbeya's `[TOC]` and `[SUBPAGES]` markers are dropped: the site has its own contents.

The app's `DocContentComponent` sets the HTML and mounts an editor on each example's placeholder. It routes the page's links in the app, and rewrites them under the base path, so they open in a new tab too.

## The editor

`<myla-editor>` (`editor/editor.component.ts`) is used everywhere: in converted pages, on the landing page, in the playground and in the exercises.

- **Loading:** it shows its code as plain text first. CodeMirror 6 (`editor/codemirror.ts`, a lazy chunk of about 20 kB) loads when the editor comes within 400 px of the screen, so a reference page with dozens of examples stays light.
- **The toolchain:** it loads on the first edit or run, not with the page.
- **Syntax:** the Myla mode (`editor/myla-language.ts`) is a CodeMirror stream language over `docs/Language/Lexical-structure.md`'s tokens. It handles f-strings with their nested expressions, numbers with suffixes, chars, attributes, and block comments that don't nest. `editor/highlight.ts` uses the same tokenizer to colour code shown without an editor (signatures, `#test` examples).
- **Actions:** Run, Test (when the code has `#test` cases), Check (for `check` and `error` examples), Reset, Copy, and Open in the playground, which carries the code in the URL. Ctrl+Enter does the editor's main action. Diagnostics from `play check` show as you type.
- **Output:** compared with the example's expected output when it has one.

`ToolchainService` fetches and compiles `play.wasm` once and shares the compiled module with Web Workers (`public/play/worker.mjs`).
- **Checks** go to one worker that lives on.
- **Runs and tests** each get a worker of their own. A Stop, or the time limit of 10 seconds, terminates it, so a program that never ends doesn't hang the page.

## The course

`learn/<NN-chapter>/` holds a chapter: `chapter.md` (`title`, `emoji`, `tagline`, then its introduction) and its exercises. An exercise is `<NN-name>.my`, with its solution beside it as `<NN-name>.solution.my`. Its header comment gives its `title`, `xp`, optionally `boss: true`, its `hint`s, and `expect` lines when it is checked by its output. The rest of the header is the instructions, in Markdown; the code below the header is what the learner starts from (`learn/README.md` has the details).

**The Check button:** an exercise with `expect` lines is solved when running it prints exactly them; any other is solved when all its `#test` cases pass (at least one). Both have a time limit of 10 seconds.

The rules are pure functions in `core/gamification.ts`, tested in `gamification.spec.ts`:
- **XP:** each hint takes 15 % off an exercise's XP, down to half; showing the solution first makes it worth nothing.
- **Levels:** 13, from Mostly Harmless to Pirate King.
- **Streaks:** days in a row with at least one solve.
- **Achievements:** 17.
- **Unlocks:** a chapter opens at 60 % of the one before; a boss once the rest of its chapter is solved. "sudo mode" opens everything.

`ProgressService` keeps the progress in `localStorage` (`myla.progress.v1`): the site has no backend. The profile page exports and imports it as a file.

## Running it locally

```bash
scripts/bootstrap.sh                 # build/myla
cd website && npm ci
npm start                            # prepares, then ng serve on http://localhost:4200
npm test                             # the content pipeline's tests (node --test), then the app's (Vitest)
npm run build:pages                  # dist/ for /myla/
npm run e2e                          # the built site in Chromium (scripts/serve.mjs serves dist/ as GitHub Pages does)
npm run check-course                 # every exercise through play.wasm
```

`npm run e2e` installs nothing. In a session with a preinstalled Chromium of another Playwright version, point the tests at it: `PW_CHROMIUM=/opt/pw-browsers/chromium npm run e2e`.

## Tests

| Where | What |
| --- | --- |
| `website/scripts/test/*.test.mjs` | The content pipeline: routes, wiki links (not inside code), anchors, examples with their output and kind, tables; the course's format |
| `website/src/**/*.spec.ts` | The gamification (levels, rewards, streaks across months, unlocks, every achievement), the search's ranking, the Myla mode's tokens, the static highlighter, the sample's output trailer |
| `website/e2e/site.spec.ts` | Every page renders without an error; the hero's program and a docs example run and match their output; an exercise is solved, earns XP and stays solved; a wrong answer isn't accepted; the search finds a method; the theme is kept; a shared playground link runs; no page scrolls sideways on a phone |
| `website/scripts/check-course.mjs` | Every exercise in `play.wasm`: unsolved as given, solved by its solution |
| `tests/burn/test_website.py` | The same with the native toolchain; the course's files well formed (one boss a chapter, at least 42 exercises); the landing page's samples print their output; `tools/doc` documents every module |

## Deploying

CI's `website` job builds the site for `/myla/`, runs all of the above, and on a push to master uploads it. The `pages` job then adds the master build's tools and the VS Code extension under `downloads/`, with `manifest.json` for the download page (`scripts/downloads.mjs`), and deploys to GitHub Pages. The repository's Pages source must be set to GitHub Actions (Settings, Pages).
