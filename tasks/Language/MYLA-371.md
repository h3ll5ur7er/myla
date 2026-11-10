---
id: MYLA-371
title: "Dotted type names in type positions (m.Point)"
type: improvement
status: done
priority: low
labels: [language, modules, decision]
---
[[Language/Modules]] says a module bound with `import` is used only as `m.member`, and that dotted type names like `m.Point` aren't supported in type positions: a type comes in with `from … import`. Two wave 2 lanes hit it (`num.ParseIntError` in [[MYLA-331]], `args.Spec` in [[MYLA-333]]): with module functions as the standard library's convention (D164), `import std.args as args` and then `args.parse(…)` read well, but naming the result's type means a second import line.

- [x] The owner's decision: allow `m.T` in type positions (D170)
- [x] The parser's type rule takes a dotted name; the checker resolves it as `m.T` (a module bound by `import … as`); the grammar, tree-sitter and the language server (hover, go-to-definition on `T`)
- [x] Tests: a parity program, error-corpus files for an unknown module and a type the module doesn't export; [[Language/Modules]] (its sentence that dotted type names aren't supported) and the skill

## Evidence

- **As built.** The parser's type rule reads `IDENT ( "." IDENT )*` into one `TRef` name (`args.Spec`, `std.deque.Deque`), its type arguments after the last segment. The loader resolves it, not the checker: `Renamer.module_type` takes the longest prefix that names a module the file binds (an `import … as` alias, or a whole path, `import std.deque`), follows a re-exported module (`shapes.dq.Deque` after `pub import .deque as dq`), and replaces the name with the export's qualified one (`std$args$Spec`), what `from std.args import Spec` binds; so the checker and the backends see an ordinary type. `impl m.Show for P` resolves its trait the same way. A table of every declaration's kind (`decl_kind_word`) tells a type from a function or constant.
- **Test first.** Before the change the parity program fails to parse at every dotted type (`parse error: expected '}', found '.'` at `spec: args.Spec,`, nine errors in all), and the three-module program too (`expected ')', found '.'` at `(shapes.dq.Deque<int>) -> int`).
- Parity: `std_module_types_by_the_module_name` (pinned `digit at 2 / empty / 3 / 2 / true / 0`: `args.Spec` as a return type and a field, `num.ParseIntError` as a parameter, an annotation and inside `Result<…>`, `[deque.Deque<int>]`, `(std.deque.Deque<int>) -> int` through a whole-path import, `deque.new<deque.Deque<str>>()` with MYLA-373) and `test_module_types_by_the_module_name`, three project modules (`deque.Deque<int>` and `set.Set<str>` as fields, `[deque.Deque<str>]`, `shapes.dq.Deque<int>` through a re-export, `shapes.Shape`, the alias `shapes.Named`, `Option<set.Set<str>>`): interpreter and native agree.
- Error corpus with pinned `.stderr` (module errors, underlining the dotted name): `module_type_unknown_module` (`unknown module 'geo' in the type 'geo.Point'…`), `module_type_not_exported` (`module 'std.args' does not export a type 'Option' (declarations are private unless marked 'pub')`), `module_type_names_a_function` (`'args.parse' is a function of module 'std.args', not a type`).
- The language server (`tools/lsp/resolve.my`): go-to-definition and hover on `T` in `m.T` give the module's declaration, on `m` the module (`test_a_module_s_type_by_the_module_s_name`: `g.Point` in a return type and in `[g.Point]`, hover `pub struct Point`).
- Own cases: `parse_type` (`args.Spec`, `std.deque.Deque<int>`, `m.0` stays `m`), the loader's `contains_byte`, `decl_kind_word`, `is_type_kind`. Grammar: `named_type = IDENT ( "." IDENT )* type_args?`, the wiki the same, tree-sitter regenerated.
- [[Language/Modules]] says what `m.T` names and shows a tested block; the skill has a row for it.

- Runs at this commit (both tasks): `scripts/bootstrap.sh` byte-identical fixed point (13,789,685 bytes); `test_compiler_parity` 182 tests OK; `scripts/test-target.py aarch64-linux test_compiler_parity` and `wasm32-wasi`: OK; `test_selfhost_parser`, `test_selfhost_checker`, `test_error_corpus` (273), `test_grammar` (10, with tree-sitter), `test_lsp` (154), `test_std_modules`, `test_doc_blocks`: OK; own cases `selfhost/checker.my` 633/633, `parser.my` 168/168, `ast.my` 56/56, `loader.my` 121/121.
- `scripts/test.sh fast`: 653 tests, 55 failures, every one from the stale `selfhost/embedded_std.my` the base 114a968 already has (its D167 change to `lib/std/map.my` isn't in the embedded copy: `map key type must be Eq and Hash, found 'K'` at `<myla>/std/map.my`), in `test_embedded_std`, `test_installed` and the suites that run the CLI's embedded library (benchmarks, project commands, packages, …). With the embedded library regenerated (`build/embed lib selfhost/embedded_std.my`, not committed) those twelve suites pass: 68 tests, OK. No seed and no embedded library here: the integrator's last commit runs `scripts/update-seed.sh` (D156).

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-417]]: three misleading diagnostics.
