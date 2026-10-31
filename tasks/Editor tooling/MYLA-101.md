---
id: MYLA-101
title: Build the VS Code extension's .vsix in CI
type: feature
status: review
priority: medium
labels: [vscode, ci]
---
Every CI run checks the VS Code extension ([[MYLA-100]], [[MYLA-99]]) and uploads its `.vsix`, so it can be installed without building it ([[Getting started]]).

- [x] A `vscode-extension` job in `.github/workflows/ci.yml`: `npm ci`, typecheck, lint, tests, `npx vsce package`
- [x] `@vscode/vsce` a devDependency, pinned in `package-lock.json`
- [x] The `.vsix` uploaded with `actions/upload-artifact` as `myla-vscode-extension`
- [x] The debugger's integration test runs there against gdb
- [x] The steps run locally exactly as in CI; the `.vsix` holds no junk

## How

The job runs in `vscode-extension/myla` on `ubuntu-latest` with Node 22 (npm's cache keyed on `package-lock.json`), Python 3.12 and gdb from apt: the integration test builds its programs with `python3 myla.py build -g` (a fresh checkout has no `build/myla`) and debugs them with gdb, so the job checks the debugger end to end without running the bootstrap. Steps: `npm ci`, `npm run typecheck`, `npm run lint`, `npm test` (which bundles first), `npx vsce package`, `unzip -l *.vsix` in the log, then `actions/upload-artifact@v4` with `if-no-files-found: error`. The other jobs are unchanged; the burn job's Node still runs `server.ts` for `test_lsp.py`, and its new `test_vscode_debugger.py` runs there only if the runner image has gdb (this job installs it, so the debugger is covered either way).

## Evidence

Run locally from a clean folder (`rm -rf node_modules out *.vsix`), the job's commands in order, with `MYLA_CLI=myla.py` standing in for a checkout without `build/`:

- `npm ci`: added 218 packages in 4 s; `npm run typecheck` and `npm run lint`: no output.
- `npm test`: tests 51, pass 51, fail 0, skipped 0 (6 s).
- `npx vsce package`: `myla-language-support-0.1.0.vsix (12 files, 126.2 KB)`; `unzip -l`:

```
     2908  extension.vsixmanifest
      538  [Content_Types].xml
     2259  extension/changelog.md
     1067  extension/LICENSE.txt
     4493  extension/readme.md
      675  extension/language-configuration.json
    10857  extension/package.json
     5480  extension/images/icon.png
    30548  extension/out/debugAdapter.js
   416073  extension/out/extension.js
    10507  extension/syntaxes/myla.tmLanguage.json
     3215  extension/snippets/myla.code-snippets
   488620  12 files
```

No sources, tests, `node_modules`, source maps or configuration files. The job has run on GitHub since: master run 41238095249 is green, 54 tests, a `.vsix` of 12 files (127 KB) uploaded as `myla-vscode-extension` (noted in the review triage of 2026-10-31).
