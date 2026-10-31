---
id: MYLA-100
title: VS Code extension overhaul
type: improvement
status: done
priority: medium
labels: [vscode]
---
Bring `vscode-extension/myla/` up to date around the debugger ([[MYLA-99]]): an accurate manifest, commands to run, test and build, a status item, a clean build, lint and tests, docs, and a `.vsix` with only what it needs. The language server start and the grammar the tests check stay as they were; the language server itself (`tools/lsp/`) is unchanged.

- [x] `package.json`: description, version 0.1.0, `repository`, `bugs`, `license` (MIT, as `editor/tree-sitter-myla`), an icon, `keywords`, categories, activation events for current VS Code, workspace trust
- [x] Commands *Run Current File*, *Run Tests in Current File*, *Build Current File*, *Debug Current File*, *Show Output* (palette and the editor title's run menu); tasks of type `myla`; a `$myla` problem matcher
- [x] Settings `myla.cliPath` and `myla.debug.gdbPath` next to `serverPath`/`compilerPath`
- [x] A language status item for the language server; the output channel
- [x] `contributes.debuggers` and `breakpoints` for the debugger
- [x] Build with esbuild, typecheck with tsc, lint with ESLint; `npm test` runs the tests
- [x] `.vscodeignore`: the `.vsix` holds the bundles and the static files, no `node_modules`
- [x] README and CHANGELOG rewritten; `vsc-extension-quickstart.md` and the placeholder *Show Extension Info* removed
- [x] The extension's unit tests run in the Python unit suite

## How

- **Sources.** `src/extension.ts` (activation: the language client as before, the status item, commands), `src/tasks.ts` (commands and the `myla` task provider), `src/debugProvider.ts` (the debug type, [[MYLA-99]]), and modules that need nothing from VS Code so node runs their tests directly: `src/toolchain.ts` (path settings, the repository, the CLI and its command lines), `src/build.ts` (debug builds, the compiler's diagnostics), `src/server.ts` (the server's command, unchanged; `tests/burn/test_lsp.py` runs it) and `src/debug/`.
- **Build.** esbuild bundles `src/extension.ts` with `vscode-languageclient` into `out/extension.js` and the standalone adapter into `out/debugAdapter.js` (minified, 406 KB and 30 KB); a `.vsix` without `node_modules` is 126 KB instead of shipping the client's dependency tree. tsc only typechecks (`noEmit`), with `erasableSyntaxOnly` and `allowImportingTsExtensions`: imports name the `.ts` files and only erasable syntax is used, so `node --experimental-strip-types` runs the sources and tests without compiling, and the Python suites can run them without `npm ci`. `src/package.json` and `test/package.json` mark those folders as ES modules for node; the bundle is CommonJS.
- **Run, test, build** are tasks (`ProcessExecution` of `myla run|test|build <file>`, in a terminal so a program can read its input), so `tasks.json` can use the type too and the `$myla` matcher (`<stage> error: …` then `--> file:line:col`) fills the Problems view. A build writes the binary next to the source, like `cc x.c -o x`.
- **The CLI** is `myla.cliPath`, else `build/myla` of the repository, else `python3 myla.py` (`chooseCli`).
- **Status.** A language status item (in the status bar's `{}` area for Myla files, pinnable) says whether the server runs, why not, and restarts it; it is the place VS Code has for a language's state, rather than a status bar item of its own.
- **Activation.** VS Code derives `onLanguage:myla` and the commands' events from the contributions; `onDebugResolve:myla` and `onDebugDynamicConfigurations:myla` are listed. In untrusted workspaces the settings that name programs come from user settings only (`restrictedConfigurations`).
- **Dependencies** are pinned in `package-lock.json`: TypeScript 6.0 (typescript-eslint doesn't support 7 yet), ESLint 10 with typescript-eslint, esbuild, `@vscode/vsce` 4, `@vscode/debugprotocol` for the protocol's types; `vscode-languageclient` stays at 9 and the engine at `^1.90.0`.

## Evidence

- `npm run typecheck` and `npm run lint`: no output. `npm test`: 51 pass.
- `test/unit/activation.test.ts` loads the bundle against a stand-in `vscode` module: activation registers exactly the commands `package.json` contributes, the `myla` task provider, both debug configuration providers and the adapter factory, and warns how to get a language server when there is no repository; the manifest's menus name existing commands and its files exist.
- The `.vsix` listing is in [[MYLA-101]].
