---
id: MYLA-633
title: "The website's embedded editor and playground"
type: feature
status: todo
priority: high
labels: [website, editor, wasm]
---
A reusable `<myla-editor>` (D208): CodeMirror 6 with a Myla language mode (keywords, types, literals, comments, f-strings, attributes) and a theme of the design system; Run, Test, Reset, Copy and Open in the playground; diagnostics from `play check` as you type; the toolchain (`play.wasm`, `tools/wasm/myla.mjs`) in a Web Worker, so a program that never ends can be stopped; output, and the expected output when the example has one.

- [ ] The worker and its service: check, run, test, a time limit, stop
- [ ] The editor component, lazy (CodeMirror loads with the first editor), many per page
- [ ] The playground page: one large editor, examples to pick, the source in the URL to share
- [ ] Tests of the worker protocol and the language mode
