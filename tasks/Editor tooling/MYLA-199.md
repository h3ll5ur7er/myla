---
id: MYLA-199
title: Dependency updates of the VS Code extension (Dependabot)
type: chore
status: review
priority: medium
labels: [vscode, dependencies, security]
---
The owner asked to include Dependabot's open updates. Its four branches (`vscode-languageclient` 10.1, `@vscode/vsce` 3.9 and 4.0 with `markdown-it`, `linkify-it` and `brace-expansion`, `undici` 7.30) all rewrite `package-lock.json` from an old base, so the bumps were applied with npm on the current branch instead of merging them.

- [x] `vscode-languageclient` ^10.1.2 (it requires VS Code ^1.91: `engines.vscode` and `@types/vscode` moved from 1.90 to 1.91; it wants a log output channel, so the *Myla* channel is created with `{ log: true }`)
- [x] `@vscode/vsce` ^4.1.0 (the branch already had ^4.0.0); `undici`, `markdown-it` and `linkify-it` are no longer in the tree; `brace-expansion` 5.0.12
- [x] `npm audit fix` (within the declared ranges): `@azure/msal-node` 7.1.2 and `@azure/identity` 4.14.1, which ends the high-severity advisory GHSA-xcx6-jx8p-x3h5 (pulled in by `@vscode/vsce`)

## Evidence

- `npm audit`: no high-severity advisory left. The 13 moderate ones are `minimatch` below `eslint`, a development tool; npm's only offered fix installs eslint 4.0, so they stay until eslint updates.
- In the freshly bootstrapped worktree: `npm run typecheck` and `npm run lint` are clean, `npm test` passes 54 of 54 (the debugger against gdb included), `npx vsce package` makes the `.vsix` (12 files, 144 KB). In the main checkout two debugger tests failed only because its `build/myla` is from 27 October.
- The Dependabot branches can be closed once this is merged: their changes are in it.
