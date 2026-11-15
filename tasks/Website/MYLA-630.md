---
id: MYLA-630
title: "The website's app: shell, design system, landing, downloads, quickstart, search"
type: feature
status: review
priority: high
labels: [website, angular]
---
The Angular app in `website/` (D208): Angular 22, standalone components, signals, zoneless, lazy routes; one design system in CSS custom properties (dark first, light too), responsive, accessible (keyboard, focus, contrast, reduced motion).

- [x] The app scaffolded in `website/`, built with `npm run build`, served as static files under a base path (GitHub Pages: `/myla/`), deep links working (`404.html`)
- [x] The shell: header with navigation and theme switch, a command palette search (Ctrl+K) over docs, reference and lessons, a footer
- [x] The landing page: a hero with a live, runnable snippet, what Myla is, the features with examples, the way in to quickstart, docs, learn
- [x] Downloads: the latest master build's tools, the VS Code extension, building from source
- [x] Quickstart: install, a first program, a project, the tools
- [x] Pop culture references that fit (42, Don't Panic, the Grand Line, …) without crowding the page
- [x] Unit tests of the services and components that hold logic

## Evidence

- `website/`: Angular 22.2 (standalone, signals, zoneless, a lazy chunk per page). The first load is 313 kB raw, 86 kB transferred (`ng build`); CodeMirror is a lazy chunk of 66 kB raw (20 kB transferred) that loads with the first editor; `play.wasm` (6.4 MB, 1.65 MB gzipped) loads on the first run or edit.
- The pages: landing (starfield hero with a live program printing 42, features, a taste in four runnable samples, the course's levels, the pipeline), quickstart (three steps, a runnable program, the wiki's Getting-started), download (the CI's tools by `downloads/manifest.json`, else building from source), docs, reference, learn, playground, a 404 with rotating quotes.
- Shell: header (navigation, Ctrl+K search, level and streak once learning, theme, GitHub), footer, toasts. The theme is set before the first paint (index.html) and kept.
- Unit tests (Vitest): 25 across gamification, search, the Myla mode, the highlighter and the samples' output trailer; `website/e2e/site.spec.ts` (Playwright): 24, every page rendering without a console error, no sideways scroll on a phone among them.
