---
id: MYLA-630
title: "The website's app: shell, design system, landing, downloads, quickstart, search"
type: feature
status: todo
priority: high
labels: [website, angular]
---
The Angular app in `website/` (D208): Angular 22, standalone components, signals, zoneless, lazy routes; one design system in CSS custom properties (dark first, light too), responsive, accessible (keyboard, focus, contrast, reduced motion).

- [ ] The app scaffolded in `website/`, built with `npm run build`, served as static files under a base path (GitHub Pages: `/myla/`), deep links working (`404.html`)
- [ ] The shell: header with navigation and theme switch, a command palette search (Ctrl+K) over docs, reference and lessons, a footer
- [ ] The landing page: a hero with a live, runnable snippet, what Myla is, the features with examples, the way in to quickstart, docs, learn
- [ ] Downloads: the latest master build's tools, the VS Code extension, building from source
- [ ] Quickstart: install, a first program, a project, the tools
- [ ] Pop culture references that fit (42, Don't Panic, the Grand Line, …) without crowding the page
- [ ] Unit tests of the services and components that hold logic
