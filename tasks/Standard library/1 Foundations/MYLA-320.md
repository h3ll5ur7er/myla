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

**Mechanism.** `implicit_modules()` in [[selfhost/loader.my]] lists `str`, `char`, `int`, `list`, `option`, `map`. `load_program_opts` loads them (`Loader.load_implicit`, through `descend` as an import of `std.<name>` resolves) after the entry unless the entry is a module of `std` (`in_stdlib`, D152's rule); a library without one skips it. They bind no name. `merge_order` puts their declarations first, so a program's own method of one of their names is the duplicate. `Loaded.std_impls` records the impls of `std` modules by node id; the checker (`build_checker_std`, which every tool now calls) counts their methods as the standard library's code (`in_std`: a method on a built-in type is named `str.trim`, not `std$…`, so before this a `std.str` method calling `__alloc` was refused in every program) and gives `duplicate method` a note naming the module and the place. The language server adds the implicit modules' methods to its method table (`Resolver.implicit_methods`), keys list and map impls by kind (`method_key`), and now types a map literal. The parser's `path_segment` takes `bool`, `str` and the sized integers in import paths ([[Language/Modules]]).

**Tests.** `tests/burn/test_implicit_imports.py` (15 tests) builds a fixture library (a copy of `lib/` plus small stand-ins of the six modules) in a scratch directory: `run`, `check`, `test` interpreted and `--native`, `build` for x86-64, aarch64 (qemu) and wasm32 (Node), the REPL, a module of the program, an explicit `import std.str as s` and `from std.str import helper` (no warning), no name bound, the duplicate with its note, an old library without the modules, a std module checked alone seeing only its imports, type keywords as path segments, and completion. Before the change 13 of the 15 failed (`type 'str' has no method 'shout'`, `expected a path segment after '.', found 'str'`, completion `[]`); after, all pass. New `#test` cases: `implicit_modules`, `has_index`, `merge_order`, `dotted_id` (loader), `path_segment` (parser), `method_key` (lsp/types).

**Measurements** (4 cores, shared machine; `myla check`, min/median of 15 runs; "fixture": `lib/` plus six generated modules of 192 methods and 1,704 lines, `std.str` 36 methods):

| Program | before, `lib/` | after, `lib/` | after, fixture |
| --- | --- | --- | --- |
| examples/hello.my | 0/1 ms | 0/1 ms | 6/8 ms |
| examples/strings.my | 1/1 ms | 1/1 ms | 8/8 ms |
| an AoC-sized program (164 lines: a grid, moves, maps) | 4/4 ms | 4/4 ms | 10/10 ms |
| tools/grammar/main.my | 45/50 ms | 51/53 ms | 51/61 ms |
| tools/lsp/main.my | 179/188 ms | 181/209 ms | 186/218 ms |
| selfhost/main.my | 355/372 ms | 370/423 ms | 375/400 ms |

Checking the six modules costs every program about 6 ms (the differences of the large programs are the machine's noise). Native binaries of all 35 examples, the AoC-sized program and `tools/grammar` are the same size with the fixture library as with a plain copy of `lib/` at a path of the same length (the library's path is in a binary, for runtime errors): code generation starts at `main` and compiles only what it reaches, so a program calling `"  hi ".trim_2()` and `xs.reversed_0()` has exactly those two of the 192 methods in its assembly (`myla_str.trim_2`, `myla___list.reversed_0__4.i32`). No dead-function pass is needed.

**Collisions.** No impl on a built-in type in `selfhost/`, `tools/`, `examples/`, the wiki's code or the burn tests' programs defines a method the wave-1 lanes plan ([[MYLA-321]]–[[MYLA-324]]); the methods there are `double`, `is_even`, `bump`, `inc`, `second`, `total`, `size`, `is_vowel`, `shout`, … `selfhost/main.my` checks with the fixture library.

**Suites.** `scripts/bootstrap.sh` reaches its fixed point; `test_implicit_imports`, `test_std_modules`, `test_doc_blocks`, `test_grammar` (with the tree-sitter CLI), `test_lsp`, `test_selfhost_parser`, `test_modules`, `test_packages`, `test_builtin_impls`, `test_error_corpus` and `test_selfhost_cli` pass, and `scripts/test.sh fast`.
