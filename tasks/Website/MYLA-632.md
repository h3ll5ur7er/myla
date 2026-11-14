---
id: MYLA-632
title: "The API reference generated from lib/std by the real parser"
type: feature
status: todo
priority: high
labels: [website, docs, tooling]
---
`tools/doc/main.my`: for each module of `lib/std`, its header comment and its public declarations (functions, structs with their fields, enums with their variants, traits, constants, type aliases, impls and their methods) with their signatures from the self-hosted parser (the language server's outline, `tools/lsp/symbols.my`), the doc comment above each, and the `#test` cases above a function as examples; written as JSON for the website ([[MYLA-631]]).

- [ ] The tool, with `#test` cases, and a burn test against a small module
- [ ] Every std module documented on the site: its wiki page (when it has one) and its generated API, the builtins' methods from the implicit modules first
