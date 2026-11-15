---
id: MYLA-633
title: "The website's embedded editor and playground"
type: feature
status: review
priority: high
labels: [website, editor, wasm]
---
A reusable `<myla-editor>` (D208): CodeMirror 6 with a Myla language mode (keywords, types, literals, comments, f-strings, attributes) and a theme of the design system; Run, Test, Reset, Copy and Open in the playground; diagnostics from `play check` as you type; the toolchain (`play.wasm`, `tools/wasm/myla.mjs`) in a Web Worker, so a program that never ends can be stopped; output, and the expected output when the example has one.

- [x] The worker and its service: check, run, test, a time limit, stop
- [x] The editor component, lazy (CodeMirror loads with the first editor), many per page
- [x] The playground page: one large editor, examples to pick, the source in the URL to share
- [x] Tests of the worker protocol and the language mode

## Evidence

- `ToolchainService` compiles `play.wasm` once and shares the module with workers (`src/worker/myla.worker.mjs`): checks in one worker that lives on, each run or test in its own, stopped by Stop or after 10 s.
- `<myla-editor>`: plain text first, CodeMirror within 400 px of the screen; Run, Test, Check, Reset, Copy, Open in the playground; diagnostics as you type after the first edit; the output compared with the expected one. The toolbar fits the editor's own width (a container query).
- The Myla mode's tests (`myla-language.spec.ts`): keywords, types, functions, builtins, constants, numbers with suffixes and bases, chars, attributes, ranges, f-strings with nested strings, block comments over lines.
- In Chromium (e2e): the hero's program prints `Life, the universe and everything: 42` in about 200 ms with the module loaded; a docs example matches its expected output; a playground link with the code in its fragment runs.
- The playground: the repository's examples to pick, standard input, sharing by link, the draft kept in the browser.
