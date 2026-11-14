---
id: MYLA-635
title: "The website in CI: built, tested and deployed to GitHub Pages"
type: feature
status: review
priority: high
labels: [website, ci]
---
- [x] A CI job: `play.wasm` built, the content generated, the app built and its unit tests run, the built site smoke-tested in Chromium (every page renders, an editor runs a program)
- [x] On a push to master: the site deployed to GitHub Pages, with the latest tools for the downloads page
- [x] [[Development/Testing]] and a wiki page for the website ([[Architecture/Website]]: how it is built, where its content comes from, how to run it locally)

## Evidence

- `.github/workflows/ci.yml`: the `website` job (bootstrap, `npm ci`, `npm test`, `npm run build:pages`, `npm run check-course`, Playwright's Chromium, `npm run e2e`; uploads the site on master) and the `pages` job (master: the site with the tools of `bootstrap` and `bootstrap-arm64` and the `.vsix`, `scripts/downloads.mjs` writing `downloads/manifest.json`, deployed with `actions/deploy-pages`). The repository's Pages source must be GitHub Actions.
- `scripts/serve.mjs` serves `dist/` as GitHub Pages does (a base path, `404.html` for any other path); the e2e tests run against it under `/myla/`.
- [[Architecture/Website]], [[Development/Testing]] (the jobs and `test_website.py`), `learn/README.md`, the README and the skill.
