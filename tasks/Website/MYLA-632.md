---
id: MYLA-632
title: "The API reference generated from lib/std by the real parser"
type: feature
status: review
priority: high
labels: [website, docs, tooling]
---
`tools/doc/main.my`: for each module of `lib/std`, its header comment and its public declarations (functions, structs with their fields, enums with their variants, traits, constants, type aliases, impls and their methods) with their signatures from the self-hosted parser (the language server's outline, `tools/lsp/symbols.my`), the doc comment above each, and the `#test` cases above a function as examples; written as JSON for the website ([[MYLA-631]]).

- [x] The tool, with `#test` cases, and a burn test against a small module
- [x] Every std module documented on the site: its wiki page (when it has one) and its generated API, the builtins' methods from the implicit modules first

## Evidence

- `tools/doc/doc.my`: 15/15 cases interpreted and `--native` (comment lines, module headers, doc comments above attributes, multi-line `#test` cases, a small module end to end with a private type and its impl left out).
- All 62 public modules in 0.5 s natively: 1424 declarations, 2576 members, 1 MB of JSON. 112 top-level declarations have no comment of their own (their module's header documents them); `zip_read`'s eight multi-line `#test` cases are found.
- `tests/burn/test_website.py`'s `Reference`: every module documented, `Vec3`'s fields, `str.split` with its doc and examples. The language server's resolution corpus passes with `tools/doc` in it.
