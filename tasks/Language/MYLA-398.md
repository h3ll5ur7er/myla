---
id: MYLA-398
title: "A bound can't name a module's trait: T: json.ToJson"
type: improvement
status: review
priority: low
labels: [language, parser, modules]
---
Found by the `#derive(Json)` lane ([[MYLA-385]]). With `import std.json as json`, `fun show<T: json.ToJson>(v: T) {}` is "parse error: expected '>' to close type parameters, found '.'". D170 lets a type position name `m.T`, but not a bound. Today's way is `from std.json import ToJson`.

- [x] A bound names a module's trait as a type names its type (`T: json.ToJson`, `I: iter.Something<T>`): the grammar, the parser, the loader's renaming, the checker, the language server; D170's row extended

## Evidence

- **Grammar** ([[grammar/myla.ebnf]], [[Language/Grammar]]): `trait_bound = IDENT ( "." IDENT )* type_args? ;`; `editor/tree-sitter-myla` regenerated (`scripts/gen_treesitter.sh` with the tree-sitter CLI): `grammar.js`, `src/grammar.json`, `src/parser.c`.
- **Parser** ([[selfhost/parser.my]], `bound_name`): a bound's trait is a dotted name, kept as written (`"json.ToJson"`), its arguments as before; `#test` cases `Show`, `json.ToJson<T>`, `a.b.Show + Eq`.
- **Loader** ([[selfhost/loader.my]], `Renamer.bounds`): a dotted bound goes through `module_type` with `want_type` false, as an impl's trait (`impl json.ToJson for P`) already did, so it becomes the trait's qualified name (`std$json$ToJson`) that `from std.json import ToJson` binds; the checker needs nothing more. A bound keeps no position of its own, so its errors are reported at its type parameter. The messages: `'json.Json' is an enum of module 'std.json', not a trait` (an article now: it said "a enum"), `module 'std.json' does not export a trait 'ToText'`, `unknown module 'geo' in the trait 'geo.Show'` (it said "in the type" for an impl's trait too).
- **Language server** ([[tools/lsp/resolve.my]], `type_params`): a dotted bound resolves like `m.T` in a type: definition of `Area` in `T: g.Area` jumps to the module's trait, of `g` to the module; hover on `T` shows `type parameter T: g.Area` (`tests.burn.test_lsp …test_a_module_s_trait_in_a_bound`).
- **Before:** `tests.burn.test_modules.TestBoundsNameAModulesTrait` failed: `parse error: expected '>' to close type parameters, found '.'` at `fun total<T: shapes.Area>` and `fun head<P: shapes.Pair<T>, T>`. **After:** it passes, interpreted and native alike: `T: shapes.Area`, a generic module trait `P: shapes.Pair<T>` (the `impl shapes.Pair<str> for Two` fixing `T`), `T: shapes.Zero + shapes.Area` with `T.zero()` and an explicit `none<Sq>()`, and `T: json.ToJson + Eq` with `json.encode(v)`: `13`, `x`, `0`, `{"x":4}`.
- **Error corpus:** `module_bound_not_a_trait.my`, `module_bound_not_exported.my`, `module_bound_unknown_module.my`, pinned.
- **Docs:** [[Language/Methods-and-traits#bounds]] (the rule, the errors, a tested example), [[Language/Modules]], [[Language/Grammar]], [[Architecture/Module-loader]], D170's row in [[Project/Decisions]] extended as this task asks; the `myla` skill's "`T: json.ToJson` is a parse error" went (both copies).
- **Not done:** a bound's failure at a call names the trait bare, `type 'Q' does not satisfy the bound 'T: ToJson' required by 'show'`, as it did for `from std.json import ToJson` (the checker's `unqualified`, kept as it was); the language server's completion after `T.` doesn't list a module trait's functions (`split_bounds` looks up the bound by its plain name).
- **Suites:** `tests.burn.test_error_corpus`, `test_grammar` (with `TREE_SITTER`: tree-sitter parses every source file and 2000 samples, `src` current), `test_modules`, `test_selfhost_parser`, `test_doc_blocks`, `test_lsp`; the bootstrap's byte-identical fixed point.
