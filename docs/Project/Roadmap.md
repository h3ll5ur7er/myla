# Roadmap

[TOC]

## How Myla got here

1. **A scripting language interpreted in Python.** The tree-walking interpreter came first and still defines the semantics.
2. **Native compilation.** An x86-64 backend without libc was added because native code would be neat and faster. It was: compiled programs run far faster than interpreted ones.
3. **Self-hosting.** Once the language could carry it, the compiler was rewritten in Myla, roadblock by roadblock, until it compiled itself to a fixed point (v1.0).
4. **After self-hosting**, the bootstrap was too slow to iterate on: building the Myla compiler took over a minute with the Python toolchain, and the first self-built round about four more. That led to three ideas:
   - rewrite the first stage in Rust to speed up and streamline the bootstrap: the origin of the [[Architecture/Rust-edition]] (removed in October 2026, [[MYLA-70]]);
   - write more sample programs, which motivated the language server ([[Architecture/Editor-tooling]]);
   - a concurrency system close to Swift's actors, which the Rust edition prototyped partially ([[MYLA-61]] records what it taught).

Measurements in October 2026 showed that the bootstrap's slowness comes from two hot spots in the Python toolchain's code generator and allocator, not from Python itself; fixing them brought the whole bootstrap down to about 8 seconds ([[MYLA-60]], [[MYLA-16]], [[Development/Bootstrap]]).

## Milestones

| Milestone | Theme | Status |
| --- | --- | --- |
| v0.0 | Python toolchain: front end, tree-walking interpreter, x86-64 compiler, `#main`/`#test` | Done |
| v0.2 | Data modelling: `enum` + `match`, tuples, generics (monomorphized), `Option`/`Result` + `?`, recursive enums, reference counting | Done |
| v0.3 | Collections and operators: lists, maps (copy-on-write), the string toolkit, `StringBuilder`, bitwise operators, casts, hex/binary/octal literals, `break`/`continue`, `const`, `assert`/`panic`/`unreachable` | Done |
| v0.4 | Abstraction: methods and `impl`, function types, lambdas and closures, `|>`/`>>`/`_`, traits, operator overloading, `#derive(Eq)`, bounds | Done |
| v0.5 | Modules and runtime: imports, `pub` and re-exports, the standard library, floats, `char` and UTF-8, freestanding I/O, generic traits, f-strings | Done |
| v0.6–v0.9 | Self-hosting bring-up: lexer, parser, checker, code generator and loader ported to Myla, each tested against the Python oracle | Done |
| **v1.0** | **Self-hosted: three-stage byte-identical fixed point** (30 June 2026) | **Done** |
| post-1.0 | Subprocesses (`std.process.run`), the self-hosted CLI with `run`/`test`/`build`, the language server, the VS Code extension, the Rust edition (removed in October 2026) | Done (July 2026), with open issues |
| October 2026 | The mid-level IR with its verifier, every function through it (D79, D85); guaranteed tail calls (`become`, D87); the project tool with Git dependencies (D73); tools in Myla (language server, REPL, grammar generator, D71) | Done |
| October 2026 | Concurrency: `async`/`await`, structured child tasks, actors, on a multi-threaded work-stealing native runtime (D89 to D97, [[MYLA-61]]) | Done |

The milestone numbering was locked by D23: self-hosting is the destination (v1.0), reached through the feature milestones. The detailed per-version designs are in [[Archive]].

## Next

1. **Quick wins**:
   - ~~make the bootstrap fast~~: done, 5 minutes → 8 seconds ([[MYLA-60]], [[MYLA-16]]);
   - ~~DWARF line tables so gdb steps through Myla source~~: done for the Python backend, `myla build -g` ([[MYLA-71]]);
   - the `myla` agent skill ([[MYLA-68]]) and GitHub Actions CI ([[MYLA-69]]), both in review.
2. **Make the existing toolchains correct.** The October 2026 review found parity and memory bugs. All the urgent ones are fixed: the Python backend's ([[MYLA-2]], [[MYLA-3]], [[MYLA-4]], and [[MYLA-10]] for diagnostics) and the self-hosted compiler's ([[MYLA-21]], [[MYLA-22]]); the Rust edition, with its own miscompiles, was removed ([[MYLA-70]]). The medium and low ones are on [[Project/Known-issues]].
3. **Close the self-hosted gaps**: ~~floats~~ (done, [[MYLA-29]]), ~~the module loader~~ (done, [[MYLA-30]]), ~~diagnostics~~ (done, [[MYLA-28]]), so that the self-hosted toolchain can replace the Python one for everyday use.
4. **Performance**: ~~string reclamation~~: done, strings are reference-counted (D62, [[MYLA-18]]).
5. **Tooling in Myla**: in the end, all tooling should be written in Myla, not only the compiler. The steps are tasks in the `Tooling in Myla` epic:
   - ~~a machine-readable grammar description, from which a generator written in Myla emits the tree-sitter grammar, tied to the compiler by tests~~: done, [[grammar/myla.ebnf]] and `tools/grammar` ([[MYLA-77]]). The parsers stay hand-written for their error messages; the grammar can't be derived from their code, so the description is the source and the tests keep both in step;
   - ~~standard-library groundwork: reading stdin and JSON~~: done ([[MYLA-78]], [[MYLA-79]], with byte ranges of strings, [[MYLA-85]]);
   - ~~a language server written in Myla on the self-hosted front end, with the Python server's tests as parity tests~~: done, with resolution by scope, imports and type and semantic tokens from the compiler's own lexer; the VS Code extension starts it ([[MYLA-80]]);
   - ~~`myla test` parity in the self-hosted CLI and a REPL~~: done ([[MYLA-81]], [[MYLA-82]]);
   - ~~finally retiring each Python tool once its Myla replacement passes the parity tests~~: done, the Python language server is removed and the Python toolchain stays as the bootstrap and the semantics reference (D71, [[MYLA-83]]).

## Ideas

Bigger directions, collected as tasks in the `Roadmap ideas` epic: three are done ([[MYLA-61]], [[MYLA-67]], [[MYLA-64]]), LLVM is planned in steps, the rest are ideas.

| Idea | Task | Notes |
| --- | --- | --- |
| Swift-style actors and structured concurrency | [[MYLA-61]] | Safety from the checker (isolation, sendability, no locks), not runtime deadlocks |
| A mid-level IR between checker and code generators | [[MYLA-67]] | Checkable reference counting, optimisations (slot reuse, register allocation, retain/drop elision, inlining), small backends |
| Optional LLVM backend, and other platforms through it | [[MYLA-62]] | Planned: decisions ([[MYLA-160]]), user code through LLVM ([[MYLA-161]]), the runtime off assembly ([[MYLA-162]]), then aarch64 Linux, macOS, wasm and Windows ([[MYLA-163]] to [[MYLA-165]], [[MYLA-158]]), and a C FFI ([[MYLA-166]]) |
| A WebAssembly target | [[MYLA-158]] | Myla and its toolchain in the browser, through LLVM |
| A website: Angular webapp with docs, an online editor and a gamified tutorial | [[MYLA-159]] | Static, data in IndexedDB; needs the wasm toolchain |
| Debugger | [[MYLA-66]] | First step: line tables ([[MYLA-71]]) |
| Better error messages | [[MYLA-65]] | Files, spans, notes, several errors per run |
| A project tool like cargo | [[MYLA-64]] | Manifest, dependencies, `myla new/build/run/test`; grows out of `selfhost/main.my` |
| A declarative GUI system inspired by SwiftUI | [[MYLA-63]] | **On hold** until everything else fits; GPU APIs would need a C FFI |

## Proposed after 1.0

Ideas not yet decided or scheduled (from the decision log and the feature catalogue in [[Archive/future-features]]):

- compound assignment `+= -= *= /= %=`, `**` and `**=`;
- custom operators (D18) and user-defined macros / attributes;
- sets (D39: as a thin layer over maps);
- by-reference closure capture with `ref` (D15, D48);
- `#derive(Ord)`, trait objects, user-defined bounds beyond operators;
- associated functions (`Type.new()`), named-field enum variants (D32), `@` bindings and range patterns (D33);
- `exec` from the language runtime beyond `std.process` (D29); the package manifest is built ([[Architecture/Project-tool]]).
