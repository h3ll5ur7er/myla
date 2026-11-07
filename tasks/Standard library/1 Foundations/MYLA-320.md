---
id: MYLA-320
title: Std methods on built-in types in every program (the implicit imports)
type: feature
status: review
priority: high
labels: [stdlib, compiler, checker, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]]. Make the method modules of [[MYLA-319]] (1) visible in every program without an `import`, as the prelude's `get` and `Option` are. The modules are `std.str`, `std.char`, `std.int`, `std.list`, `std.option` and `std.map`. This is the one compiler task of wave 1. The library lanes don't wait for it: they test with an explicit `import`, and this task removes the need.

- **Owns:** `selfhost/` (loader, checker, LSP)
- **Needs:** [[MYLA-319]]

- [x] The loader adds the implicit modules to every program (not to the modules of `std` itself, which import what they use); a program's own method of the same name on the same type is the existing duplicate error
- [x] `myla check` time and native binary size measured before and after on the examples and an AoC-sized program; methods a program doesn't call cost nothing in its binary (if they do, the dead-function pass fixed first)
- [x] The language server completes the implicit methods
- [x] [[Language/Modules]] and [[Language/Standard-library]] updated
- [x] An import path's segment may be a primitive type's keyword, so `import std.str as s` and `from std.str import f` parse (found by the std.str lane): the parser, `grammar/myla.ebnf`, [[Language/Grammar]] and the tree-sitter grammar

## Evidence

**Mechanism.** `implicit_modules()` in [[selfhost/loader.my]] lists `str`, `char`, `int`, `list`, `option`, `map`. `load_program_opts` loads them (`Loader.load_implicit`, through `descend` as an import of `std.<name>` resolves) after the entry unless the entry is a module of `std` (`is_std_module`: under the root's `std/`, D152's rule; `in_stdlib` took any file under the root); a library without one skips it. They bind no name. `merge_order` puts their declarations first, so a program's own method of one of their names is the duplicate. `Loaded.std_impls` records the impls of `std` modules by node id; the checker (`build_checker_std`, which every tool now calls) counts their methods as the standard library's code (`in_std`: a method on a built-in type is named `str.trim`, not `std$…`, so before this a `std.str` method calling `__alloc` was refused in every program) and gives `duplicate method` a note naming the module and the place. The language server adds the implicit modules' methods to its method table (`Resolver.implicit_methods`), keys list and map impls by kind (`method_key`), and now types a map literal. The parser's `path_segment` takes `bool`, `str` and the sized integers in import paths ([[Language/Modules]]).

**Tests.** `tests/burn/test_implicit_imports.py` (16 tests) builds a fixture library (a copy of `lib/` plus small stand-ins of the six modules) in a scratch directory: `run`, `check`, `test` interpreted and `--native`, `build` for x86-64, aarch64 (qemu) and wasm32 (Node), the REPL, a module of the program, an explicit `import std.str as s` and `from std.str import helper` (no warning), no name bound, the duplicate with its note, an old library without the modules, a std module checked alone seeing only its imports, an implicit module's ill-typed case left out of a program but reported by `myla test` of its file, type keywords as path segments, and completion. Before the change 13 of the first 15 failed (`type 'str' has no method 'shout'`, `expected a path segment after '.', found 'str'`, completion `[]`); after, all pass. New `#test` cases: `implicit_modules`, `has_index`, `merge_order`, `dotted_id`, `is_std_module`, `fun_without_tests` (loader), `path_segment`, `skip_group`, `parse_source_with` (parser), `method_key` (lsp/types).

**Measurements with the real modules** (the integration branch at bfb0b82: 6,618 lines, 2,083 `#test` cases, 1,826 of them std.int's; 4 cores, shared, load 1 to 2; `myla check`, min/median of 15 runs; "before": the same toolchain with a copy of `lib/` without the six, which is what a program cost before; native sizes in bytes, the two copies at paths of the same length):

| Program | check, before | check, after | binary, before | binary, after |
| --- | --- | --- | --- | --- |
| examples/hello.my | 0.4/0.5 ms | 26.1/31.8 ms | 18208 | 18208 |
| examples/strings.my | 1.2/1.3 ms | 27.1/32.8 ms | 24224 | 24224 |
| an AoC-sized program (164 lines: a grid, moves, maps) | 3.3/4.0 ms | 28.9/34.4 ms | 29304 | 29304 |
| tools/grammar/main.my | 46.2/52.8 ms | 77.9/86.1 ms | 297024 | 297024 |
| tools/lsp/main.my | 191.3/211.9 ms | 212.5/256.3 ms | 1839912 | 1839912 |
| selfhost/main.my | 423.8/457.4 ms | 414.6/479.2 ms | 3015432 | 3015432 |

- The cases: as the integrator's measurement of std.int showed, they were more than half of a module's cost. A program leaves them out: the loader parses a module it loads for the implicit set with `skip_tests` (the parser skips a case's brackets without building them) and drops the cases of an implicit module an explicit import loaded first. hello.my with all six: 36 ms with the cases checked, 31 ms with them dropped after parsing, 26 to 30 ms skipped unparsed, 24 ms with the `#test` lines removed from the files (the rest is lexing them). A `std.char` case that doesn't type-check broke every program before (its method was left out: `type 'char' has no method 'is_vowel'`); now only `myla test lib/std/char.my` reports it.
- By module, hello.my with only one of them: none 0.5 ms, str 3.5, char 2.3, int 23.2, list 6.8, option 2.5, map 1.4, all six 34.8 (before the cases were skipped). What remains is checking the methods' bodies, and std.int, one impl per width, is two thirds of it. Bringing it down further is std.int's shape (fewer copies per width) or checking a method's body only when a program calls it, a checker change of its own.
- Binaries are the same size, byte for byte apart from the library's path, which a binary holds for runtime errors. Code generation starts at `main` and compiles only what it reaches: with the earlier fixture of 192 methods, a program calling `"  hi ".trim_2()` and `xs.reversed_0()` has exactly those two in its assembly (`myla_str.trim_2`, `myla___list.reversed_0__4.i32`). No dead-function pass is needed.
- The bootstrap reaches its fixed point with the six modules loaded into the compiler itself.

**Collisions.** No impl on a built-in type in `selfhost/`, `tools/`, `examples/`, the wiki's code or the burn tests' programs defines a method the wave-1 lanes plan ([[MYLA-321]]–[[MYLA-324]]); the methods there are `double`, `is_even`, `bump`, `inc`, `second`, `total`, `size`, `is_vowel`, `shout`, … `selfhost/main.my` checks with the fixture library.

**`myla test` of a file ran the implicit modules' cases** (the integrator's full suite at 7c5a90e: `myla test examples/constants.my` ran 2,012 cases, about 60 tests failed). The interpreter and the native harness take a case as the file's own when its function's name has no module id, and a method on a built-in type is `str.trim` in every module. Leaving the implicit modules' cases out fixes it: `myla test examples/constants.my` runs its 12 cases, interpreted and `--native`, and `myla test lib/std/int.my --stdlib lib` still runs std.int's 1,826, interpreted and `--native` (that file is the entry and a module of `std`, so it gets no implicit modules). `test_implicit_imports.test_test_cases` pins the count. A user module's `impl` on a built-in type with `#test` cases, imported by the file tested, has the same problem and still has it: the runners should decide by the declaration's file.

**Suites** (rebased onto 7c5a90e). `scripts/bootstrap.sh` reaches its fixed point; `test_implicit_imports`, `test_std_modules`, `test_doc_blocks`, `test_grammar` (with the tree-sitter CLI), `test_lsp`, `test_selfhost_parser`, `test_modules`, `test_packages`, `test_builtin_impls`, `test_selfhost_cli`, `test_test_functions`, `test_project_commands`, `test_test_native`, `test_unit_type` and `test_test_names` pass. `scripts/test.sh fast`: 619 tests, all passing but the two diagnostics std's new methods changed (`test_builtin_methods`' `contains_on_a_list`, std.list's `contains`; `examples/errors/type_pop_non_list.my`, now with `help: did you mean 'pow'?`), which the integrator takes, and `test_test_native`'s report under load (a child's output racing; it passes alone).
