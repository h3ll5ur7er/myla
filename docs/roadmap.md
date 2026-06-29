# Myla Roadmap & Status

The living source of truth for **what is built, what is in progress, what is
planned**, and **which decisions we have locked in**. Update this file as work
progresses.

Related docs: [language-spec.md](language-spec.md) · [grammar.md](grammar.md) ·
[architecture.md](architecture.md) · [future-features.md](future-features.md) ·
[self-hosting.md](self-hosting.md) ·
[v0.2 data modeling](v0.2-data-modeling.md) ·
[v0.3 collections & ops](v0.3-collections-and-ops.md) ·
[v0.4 abstraction](v0.4-abstraction.md) ·
[v0.5 modules & runtime](v0.5-modules-and-runtime.md) ·
open questions in [clarification_needed.md](clarification_needed.md).

_Last updated: 2026-06-28 (**v0.2 complete**; **v0.3 complete** — all five phases landed: bitwise/shift operators `& | ^ ~ << >>`, numeric casts `x as T`, `0x`/`0b`/`0o` integer literals with `_` separators, `break`/`continue`, module-level `const`, the `assert`/`panic`/`unreachable` intrinsics, **lists `[T]`**, **maps `[K: V]`** (copy-on-write + reference counting, open-addressing hash table, monomorphization), and the **string toolkit** (char literals, byte indexing `s[i] -> uint8`, `len(str)`, `str + str` concat, `format`, and a refcounted CoW `StringBuilder`), all end-to-end with interpreter/native parity. **v0.4 design locked** ([v0.4-abstraction.md](v0.4-abstraction.md)) — methods/`impl`, lambdas/closures, pipelines, traits + operator overloading; sub-decisions X1–X9 → **D45–D53**. **v0.4.1 (methods & `impl`) landed** — inherent methods on struct/enum incl. generic `impl<T>`, `self`/`var self`, read-only methods on builtins, interpreter↔native parity. **v0.4.2 (function types, lambdas & closures) landed** — `(…) -> R` types, lambdas (expr + block body), by-value/deep-immutable capture (D48), the 16-byte `(code_ptr, env_ptr)` fat value + refcounted env cell (D49), plain `fun`s as first-class values, indirect calls, generic higher-order functions, interpreter↔native parity + arena-reclaim stress. **v0.4.3 (pipelines, composition & partial application) landed** — `|>` pipeline (lowest precedence, splices left as 1st arg), `>>` operand-typed composition (D24/D50), `_` partial-application holes (D51, no currying, works on methods); pure desugaring over v0.4.2 lambdas/calls via the shared post-check pass, interpreter↔native parity + arena-reclaim stress. **v0.4.4 (traits + operator overloading + `#derive(Eq)`) landed — v0.4 abstraction milestone complete** — user `trait` / `impl Trait for T` with conformance + coherence checking (no orphan rule), a fixed built-in operator-trait set (`Add/Sub/Mul/Div/Rem/Eq/Ord`) so `a OP b` desugars uniformly to a method call (primitives keep built-in operators; `Eq`/`Ord` lift D37), `#derive(Eq)` synthesizing structural equality for struct/enum, and limited generic bounds `<T: Trait>` checked at the call site with runtime dispatch (interpreter) / monomorphized lowering (native); interpreter↔native parity + arena-reclaim stress (D52/D53, X8/X9). **v0.5 scope being set** — re-exports via a `pub`-prefixed import (`pub import … as …` / `pub from … import …`, `as` required on `pub import`) → **D54**; restricted generic traits (`trait Comparable<T>`, ≤1 impl/type, no overload resolution) → **D55**; **floats** (`float32`/`float64`, `float` alias, `fN` suffixes, per D19) pulled into v0.5 → **D56**; package/module resolution corner cases → **D57**; string interpolation `f"…"` over `format` → **D58**. Full v0.5 design now in [v0.5-modules-and-runtime.md](v0.5-modules-and-runtime.md)._

---

## Status legend

| Symbol | Meaning |
|--------|---------|
| Done | Fully implemented and documented |
| In progress (NN%) | Started; approximate completion in percent |
| Planned | Agreed/scheduled, not started |
| Proposed | Idea documented, not yet decided |
| Decided | Design decision locked (may not be implemented yet) |

> "Progress %" is a rough engineering estimate, not a precise metric. For a
> design-phase milestone it reflects how much of the design is settled; for an
> implementation milestone it reflects code + tests + docs.

---

## Where we are now

**Current milestone: v0.0.3 — native compiler.** The full v0.0 front end
(lexer, parser, type checker), the tree-walking interpreter, **and the x86-64
compiler** are implemented and tested: `myla run`, `myla test`, and
**`myla build`** all work end-to-end, and every example program produces
identical output under the interpreter and the compiled native binary.

Implementation progress:
- Package layout under `src/myla/` with `myla.py` entry point and a
  `unittest`-based harness under `tests/` (no third-party deps).
- `errors.py` (positioned diagnostics with caret rendering), `tokens.py`
  (`TokenKind`, `Token`, keyword table), and `lexer.py` (full v0.0 lexical
  grammar: identifiers/keywords, sized-type keywords, integer literals with
  `iN`/`uN` suffixes, strings with escapes, all operators incl. `#`/`[`/`]`,
  line and block comments, newline handling, line/column tracking).
- `ast.py` (one dataclass per construct, positions excluded from equality) and
  `parser.py` (recursive descent + precedence climbing: declarations with
  attributes, statements, full expression precedence, struct-literal gating in
  control-flow headers, `else`/`else if`, lvalue validation).
- `types.py` — type representations (sized ints, `bool`, `str`, structs) and the
  type checker: global struct/function/alias tables (order independent), `int`
  alias + `typealias` resolution with cycle detection, flexible integer-literal
  typing + width fitting, no implicit int mixing, lvalue/mutability checks,
  `#main`/`#test` validation, and single-entry-point resolution. Annotates each
  expression with a `resolved_type`.
- `interpreter.py` — tree-walking evaluator: per-width integer wrapping,
  truncating division/modulo (toward zero), struct **value semantics** (copy on
  bind/assign/arg/return/construct), `print`, and a `#test` runner.
- `compiler/codegen_x86.py` — single-pass x86-64 GAS/AT&T code generator (no
  libc): stack-based calling convention, 8-byte canonical scalar slots with
  width-aware wrapping, signed/unsigned arithmetic + comparisons, truncating
  division with a divide-by-zero trap, structs by value (pointer-passed params,
  sret returns, `rep movsq` copies), short-circuit `&&`/`||`, and emitted
  `write`/`exit` syscall helpers for `print` (int/uint/bool/str) + string
  equality. `compiler/__init__.py` drives `as`/`ld` to produce a native ELF.
- `cli.py` with working `tokenize`/`parse` debug commands and end-to-end
  `run`/`test`/`build` (`--keep-asm` to inspect output); `repl` remains a stub.
- 151 passing tests: lexer/parser/type-checker/interpreter/codegen units
  (`tests/unit/`), parse-every-example integration (`tests/integration/`), and
  **burn tests** that run every example under the interpreter *and* the native
  binary, asserting identical stdout plus codegen corner cases (`tests/burn/`).

**Next up: the post-v0.0 feature build-out that leads to self-hosting.** The
[self-hosting plan](self-hosting.md) works backwards from the existing toolchain
to show that re-implementing Myla in Myla **depends on** the v0.2–v0.5 features
(enums/match, generics, collections, strings, bitwise/casts, methods, modules,
a freestanding I/O runtime). Self-hosting is therefore the **destination (v1.0)**,
not the immediate next step — superseding the old "v0.1 = self-host" framing
(locked, D23). Newly-scoped prerequisites (bitwise ops, numeric
casts, `break`/`continue`, methods/`impl`, `const`, char/byte lexing, I/O) are in
[future-features.md](future-features.md) §11–§18.

```mermaid
flowchart LR
    d003["v0.0.3 compiler (done)"] --> v02["v0.2 data modeling"]
    v02 --> v03["v0.3 collections + strings + ops"]
    v03 --> v04["v0.4 abstraction"]
    v04 --> v05["v0.5 modules + runtime"]
    v05 --> bringup["v0.6–v0.9 self-hosting bring-up"]
    bringup --> v10["v1.0 self-hosted"]
```

---

## Milestone status

| Milestone | Description | Status |
|-----------|-------------|--------|
| v0.0.0 | Architecture & design (spec, grammar, architecture, examples) | Done |
| v0.0.1 | Scaffolding: Python package layout + unit/integration/burn test harness | Done |
| v0.0.2 | Front end + tree-walking interpreter; `myla run`/`test`; burn-tests pass | Done |
| v0.0.3 | Working x86-64 compiler; `myla build`; output matches interpreter | Done |
| (in v0.0.2) | `#main` / `#test` attributes + `myla test` runner | Done (pulled into v0.0 per D10) |
| v0.2 | Data modeling: `enum`+`match`, tuples, generics, `Option`/`Result` | **Done** — tuples, enums/`match`, recursive enums (heap-boxed), reference counting, **generics** (monomorphized): functions (v0.2.4a) + structs/enums (v0.2.4b), and the **`Option`/`Result` prelude + `?` (v0.2.4c)** complete (interpreter+compiler+tests) (see [v0.2-data-modeling.md](v0.2-data-modeling.md)) |
| v0.3 | Collections, strings & ops: lists/maps/sets, string toolkit, refcounting, bitwise, casts, `break`/`continue`, `const`, `assert` | **Done** (Tier B+C) — v0.3.1–v0.3.5 all landed: bitwise/shift, `x as T`, `0x`/`0b`/`0o` literals, `break`/`continue`, `const`, `assert`/`panic`/`unreachable`, lists `[T]`, maps `[K: V]`, and the string toolkit (char literals, byte indexing, `len(str)`, `+` concat, `format`, `StringBuilder`). Sets deferred (D39). |
| v0.4 | Abstraction: methods/`impl`/traits, lambdas/closures, pipelines | **Complete (Tier D)** — v0.4.1 methods/`impl` + v0.4.2 function types/lambdas/closures + v0.4.3 pipelines/composition/partial application + v0.4.4 traits + operator overloading + `#derive(Eq)` + generic bounds all landed, interpreter↔native parity |
| v0.5 | Modules & runtime: imports + `pub` re-exports + stdlib, char/byte model, freestanding I/O, floats, restricted generic traits, string interpolation | **Complete (Tier E)** — v0.5.1 modules/imports + v0.5.2 floats + v0.5.3 `char`/UTF-8 + v0.5.4 freestanding I/O (`std.io`/`std.process`/`std.fs`) + v0.5.5 restricted generic traits + v0.5.6 `f"…"` interpolation all landed, interpreter↔native parity |
| v0.6–v0.9 | Self-hosting bring-up: port the toolchain to Myla, differentially tested | **In progress (Tier F)** — v0.6a **done**: canonical token dump oracle (`myla tokenize --canonical`) + the Myla-written lexer reach byte-for-byte token parity. v0.6b **done**: canonical AST dump oracle (`myla parse --canonical`) + the Myla-written parser (`selfhost/parser.my`, AST as `enum` sum types in `selfhost/ast.my`) reach byte-for-byte structural-AST parity across examples, error corpus, stdlib, and self-parsing, on both interpreter and native backends. v0.7 **in progress**: checker oracle (`myla check --canonical` → `ok` / `err <line> <col> <kind>`) landed; AST metadata model locked as wrapper structs `{id,line,col,kind}` (NodeId + positions) with the parser/dump gates still byte-identical; the checker port itself is the active work |
| v1.0 | Self-hosted: Myla compiles Myla (three-stage fixed point) | Planned (destination) |
| post-1.0 | Custom operators, compound-assign/`**` sugar, user-defined macros | Proposed |

> See [self-hosting.md](self-hosting.md) for the dependency analysis behind this
> ordering and the differential-testing strategy. Numbering is locked (D23).

### v0.0.0 remaining work
- Done: language spec, formal grammar, architecture doc, per-feature examples,
  future-features design, roadmap + clarification tracking.
- Open: resolve the design questions in
  [clarification_needed.md](clarification_needed.md) that affect post-v0.0 work
  (none block starting v0.0.1).

---

## Feature status matrix

### v0.0 core language (target: v0.0.2 interpreter / v0.0.3 compiler)

| Feature | Designed | Implemented | Target |
|---------|----------|-------------|--------|
| `fun` function declarations | Done | Done (interp+native) | v0.0.2 |
| `let` / `var` bindings + mutability | Done | Done (interp+native) | v0.0.2 |
| Explicitly sized integers (`int8`..`uint64`) | Done | Done (interp+native) | v0.0.2 |
| Integer literal type suffixes (`255u8`, `123i64`) | Done | Done (interp+native) | v0.0.2 |
| `int` as alias of `int32` | Done | Done (interp+native) | v0.0.2 |
| `typealias` declarations | Done | Done (interp+native) | v0.0.2 |
| `#main` / `#test(...)[...]` attributes | Done | Done (interp+native) | v0.0.2 |
| `bool`, `str` (length-prefixed, immutable, literals + `print`) | Done | Done (interp+native) | v0.0.2 |
| Arithmetic / comparison / logical operators | Done | Done (interp+native) | v0.0.2 |
| `if` / `else if` / `else` | Done | Done (interp+native) | v0.0.2 |
| `while` | Done | Done (interp+native) | v0.0.2 |
| `for ... in` ranges | Done | Done (interp+native) | v0.0.2 |
| `struct` decl / construction / field access | Done | Done (interp+native) | v0.0.2 |
| `print` builtin | Done | Done (interp+native) | v0.0.2 |
| `return` (incl. exhaustiveness) | Done | Done (interp+native) | v0.0.2 |
| Native codegen (x86-64, GAS, `as`/`ld`) | Done | Done (compiler) | v0.0.3 |
| REPL (`myla repl`) | Partially | Planned | later |
| Test runner (`myla test` via `#test`) | Done (design) | Done (interpreter) | v0.0.2 |

### Post-v0.0 features

Targets follow the [self-hosting](self-hosting.md) dependency ordering (Tier A–E
→ §3). "§N" points at [future-features.md](future-features.md).

| Feature | Status | Target | Notes |
|---------|--------|--------|-------|
| Algebraic data types (`enum`) + `match` | Done (v0.2) | v0.2 | Enums + full `match` done (expr value D30; payloads D32; wildcard/binding/literal/enum/tuple/struct/nested/or-patterns + guards D33; exhaustiveness + redundancy). **Recursive enums heap-boxed (v0.2.3)**: self-referential payload edges become 8-byte heap pointers; pure struct/tuple cycles still rejected. **Reference counting (v0.2.3b)**: refcounted heap cells with a free list, retain-on-share / drop-at-scope-exit, freed at zero — build/discard loops run in bounded memory. Interpreter + native parity. |
| Tuples + multiple return (`return a, b`) | Done (v0.2) | v0.2 | Arity ≥ 1, `(x,)` 1-tuple, no unit type (D35); indexing, destructuring, value semantics — interpreter + native parity |
| Generics via monomorphization | Done (v0.2) | v0.2 | Strategy locked (D13); inferred at call sites (D34). **Functions (v0.2.4a) + structs/enums (v0.2.4b) done**: `fun id<T>`, `struct Box<T>`, `enum List<T>` (incl. recursive + RC), call-site/value inference, monomorphized per concrete instantiation (functions *and* layouts) before codegen; interpreter runs them by erasure. |
| Error handling: `Result`/`Option` + `?` | Done (v0.2.4c) | v0.2 | (D16); same-carrier `?` (D36). `Option`/`Result` injected by the prelude (variants constructible unqualified: `Some`/`None`/`Ok`/`Err`); `?` desugars to a `match` once its carrier is known (success → value, failure → `return`). Monomorphized like any generic enum; interpreter + native parity. |
| Collections: `[T]` list | Done (v0.3.3) | v0.3.3 | Literals (`[]` typed by context), `len`/`xs[i]`/`xs[i]=v`/`push`/`pop`/`for…in`; value semantics with copy-on-write under RC; bounds-checked (traps); monomorphized per element type (D14/D38/D39); Tier B |
| Collections: `[K: V]` map | Done (v0.3.4) | v0.3.4 | Literals (`[k: v]`/`[:]` typed by context), primitive keys (D37), `len`/`m[k]`/`m[k]=v`/`get`/`contains`/`remove`/`keys`/`for k in m`; value semantics with copy-on-write under RC; open-addressing hash table (FNV-1a + linear probing, rebuild deletion); `m[k]` read traps on absent key; monomorphized per `(K,V)` (D14/D38/D39); Tier B |
| Collections: sets | Deferred | v0.4+ | Sets deferred (D39) — a set can be a thin wrapper over a map later; revisit on concrete need |
| Memory model: reference counting | Decided | v0.3 | (D12); Tier B |
| `str`: builder + byte-indexing + `format` + concat | Done (v0.3.5) | v0.3.5 | v0.0 `str` is length-prefixed immutable (D21). Char literals (`'a'`/`'\n'`, default `uint8`), byte indexing `s[i] -> uint8` (traps OOB), `len(str)`, `str + str` concat, `format(fmt, …)` (literal fmt, compile-checked holes); refcounted CoW `StringBuilder` (`append`/`append_byte`/`len`/`build`). Concat/`format` results are non-refcounted heap (arena-resident, by design); slices/views and the Unicode `char` type deferred to v0.5. Tier B |
| Bitwise & shift operators `& \| ^ ~ << >>` | Done (v0.3.1) | v0.3.1 | Integer-only; bitwise tighter than comparison (`&`>`^`>`\|`), shifts below; signed `>>` arithmetic; const out-of-range shift is an error, runtime amounts masked to width. `<<`/`>>` parsed as adjacent `<`/`>` (D24); Tier C |
| Explicit numeric casts (`x as T`) | Done (v0.3.1) | v0.3.1 | numeric→numeric only, wrap/extend via shared width logic; no implicit mixing (D4; D26); Tier C |
| `break` / `continue` | Done (v0.3.1) | v0.3.1 | In `while`/`for`; rejected outside a loop; native backend drops loop-body heap owners on early exit; Tier C |
| Numeric literal bases `0x`/`0b`/`0o` (+ `_` separators) | Done (v0.3.1) | v0.3.1 | Ordinary integer literals; reuse the `iN`/`uN` suffixes (D43); Tier C |
| Module-level `const` | Done (v0.3.2) | v0.3.2 | `const NAME: T = <constexpr>`, explicit type; checker folds the value (literals/const-refs/arith/bitwise/cast/logical), rejects cycles + non-const initializers + const div-by-zero; interpreter uses a global env, native inlines the value (D28); Tier C |
| `assert` / `panic` / `unreachable` | Done (v0.3.2) | v0.3.2 | `assert(cond[, msg])`, `panic(msg)`, `unreachable()`; `panic`/`unreachable` diverge (treated like `return`); native `__panic` writes to stderr + `exit(1)`, interpreter raises a runtime error; reserved builtins; Tier C |
| Methods + `impl` (static dispatch) | **Done (v0.4.1)** | v0.4.1 | Inherent methods on struct/enum (incl. generic `impl<T>`) + read-only `self` on builtins; `self`/`var self` (D47), no orphan rule (D45), no UFCS (D46); interpreter↔native parity. [v0.4-abstraction.md](v0.4-abstraction.md) §1, §9; Tier D |
| Traits (incl. operator overloading) | **Done (v0.4.4)** | v0.4.4 | User `trait` + `impl Trait for T` (conformance + coherence, no orphan rule D45); fixed operator-trait set with uniform `a OP b` → method desugaring (primitives unchanged, `Eq`/`Ord` lift D37); `#derive(Eq)` structural equality; limited generic bounds `<T: Trait>` checked at the call site (D52/D53, X8/X9); interpreter↔native parity; Tier D. [v0.4-abstraction.md](v0.4-abstraction.md) §9 |
| Lambdas / closures + function types | **Done (v0.4.2)** | v0.4.2 | `(…) -> R` types + lambdas (expr/block body); by-value, deep-immutable capture (D48); 16-byte `(code_ptr, env_ptr)` fat value + refcounted env (D49); plain `fun`s as values, indirect calls, generic higher-order fns; interpreter↔native parity; `ref` later (D15); Tier D. [v0.4-abstraction.md](v0.4-abstraction.md) §9 |
| Functional pipelines `|>` / composition / `_` partial app | **Done (v0.4.3)** | v0.4.3 | `|>` lowest-prec splices left as 1st arg; `>>` compose-by-type (D50, D24); `_` partial app, no currying, works on methods (D51); pure desugaring to v0.4.2 lambdas via the shared post-check pass; interpreter↔native parity; Tier D. [v0.4-abstraction.md](v0.4-abstraction.md) §9 |
| Modules / imports (explicit, Python-like) | Done (v0.5.1) | v0.5 | `from … import …` (aliases, `pub` visibility, `pub from` re-exports) **and** whole-module `import a.b.c [as x]` with `x.member` access + `pub import … as …` module re-exports; D57 resolution rules; qualified-merge linker; interpreter↔native parity (D17/D22/D54/D57). Module-qualified types/patterns use `from` (not dotted). Tier E. [v0.5-modules-and-runtime.md](v0.5-modules-and-runtime.md) §1, §12 |
| Generic traits (restricted, ≤1 impl/type) | **Done** (v0.5.5) | v0.5 | `trait Comparable<T>` with type parameters; `impl Comparable<int32> for T` substitutes the trait params into conformance checking. Coherence: at most one `impl` of a trait per type (arguments ignored), so `x.compare(y)` needs no overload resolution — the single impl fixes `T`. Pure front-end (parser + checker); methods lower to ordinary functions, so no new dispatch/runtime (D55, refines D53). Interpreter↔native parity (`examples/generic_traits.my`). Tier E. [v0.5-modules-and-runtime.md](v0.5-modules-and-runtime.md) §6 |
| String interpolation `f"…{expr}…"` | **Done** (v0.5.6) | v0.5 | Sugar over `format`: `f"…"` prefix, arbitrary `{expr}`, `{{`/`}}` literals, no format specs yet, single-line. Implemented entirely in the lexer — an `f"…"` lowers in place to the token stream of a `format(fmt, args…)` call (balanced-brace split; each hole re-lexed as an expression), so no new token/AST/checker/runtime; interpreter↔native parity is automatic (`examples/interpolation.my`). (D58); Tier E. [v0.5-modules-and-runtime.md](v0.5-modules-and-runtime.md) §7 |
| Standard library (`std`) | Planned | v0.5 | Needs modules; Tier E |
| `char` type (Unicode scalar) + UTF-8 lexing | **Done** (v0.5.3) | v0.5 | Dedicated `char` (D25, refines D42): Unicode-scalar literals + `\u{…}`, `char`↔int `as`, comparisons, UTF-8-glyph `print`/`format`, ASCII byte-compat; `chars(s) -> [char]` UTF-8 codepoint iteration; bytes view stays `s[i]`/`len(s)`. Interp↔native parity. [v0.5-modules-and-runtime.md](v0.5-modules-and-runtime.md) §4 |
| Freestanding I/O runtime (file/`argv`/stderr/exit) | **Done** (v0.5.4) | v0.5 | No-libc syscalls, defer `exec` (D29); Tier E. Bundled `std/` stdlib + `std.io` (`write`/`println`/`eprint`/`eprintln`) + `std.process.exit`/`args()` + `std.fs.read_to_string -> Result<str, IoError>` over `__write`/`__exit`/`__args`/`__read_file` primitives (argc/argv stashed at `_start`; `open`/`fstat`/`read`/`close` for files). `Interpreter.run()` returns the exit status; `myla run file.my [args…]` forwards argv; the `Result`/`IoError` carrier is pure Myla. Interp↔native parity on stdout/stderr/exit/argv/file-contents incl. errno paths. [v0.5-modules-and-runtime.md](v0.5-modules-and-runtime.md) §5 |
| Floats (`float32`/`float64`, `float` alias, `fN` suffixes) | **Done** (v0.5.2) | v0.5 | Excluded from v0.0 (D19); scheduled into v0.5 (D56); IEEE-754 SSE2 arithmetic/compare/`as`, round-trippable plain-decimal `print`/`format` (interp↔native parity). [v0.5-modules-and-runtime.md](v0.5-modules-and-runtime.md) §3 |
| Custom operators | Postponed | post-1.0 | Beyond 1.0 (D18) |
| Compound assignment `+= -= *= /= %=`, `**`, `**=` | Proposed | post-1.0 | Pure sugar; not needed for self-hosting |
| `++` / `--` | Dropped | — | Possible user-defined custom operator post-1.0 (D9) |
| User-defined macros / metaprogramming | Proposed | post-1.0 | After self-hosting |

---

## Decision log (locked decisions)

Newest first. These are settled; revisiting requires a deliberate new decision.

| # | Date | Decision | Rationale |
|---|------|----------|-----------|
| D58 | 2026-06-28 | **String interpolation `f"…{expr}…"` (sugar over `format`)**: an `f"…"` prefix; arbitrary expressions inside `{ }`; `{{`/`}}` are literal braces; **no** format specs in v0.5 (parity with `format`); single-line only. Lowers at parse time to `format(fmt, args…)` (lexer balanced-brace split, each slice re-parsed as an expression). | Opt-in prefix keeps plain strings / existing `format` calls untouched; zero new runtime, reuses the `format` checks + both backends; the lexer scan is the only real cost so it lands last. [v0.5-modules-and-runtime.md](v0.5-modules-and-runtime.md) §7 |
| D57 | 2026-06-28 | **Package/module resolution corner cases**: files=modules, dirs=packages; an optional `foo/foo.my` package-root module defines a package's public surface via `pub import` (no implicit glob re-export); a file/dir name clash in one parent → compile error; the **project root = the entry-file's directory** (no manifest yet); reserved roots (`std`, prelude) are **shadow-protected** (a project dir shadowing one is an error); `from a.b import c` resolves **module-before-item**; import cycles are allowed (only `const`-init cycles error, D28). | Pins the filesystem↔namespace mapping left open by D17/D22 with the simplest unambiguous rules; reuses D54 re-exports for package surfaces instead of inventing `__init__` semantics. [v0.5-modules-and-runtime.md](v0.5-modules-and-runtime.md) §1.4 |
| D56 | 2026-06-28 | **Floats pulled into v0.5 scope**: implement `float32`/`float64` (+ the `float` alias and `f32`/`f64` literal suffixes) as designed in D19, in v0.5 alongside modules & runtime. (schedules D19/D20) | The self-hosted compiler/stdlib and numeric code benefit; v0.5 is the natural home now that the integer/abstraction tiers are complete |
| D55 | 2026-06-28 | **Generic traits (restricted) scheduled for v0.5**: a `trait` may take type parameters (`trait Comparable<T>`) but is implementable **at most once per type** — no multiple `impl`s of the same trait for one type with different arguments, hence **no overload resolution**. Needs trait-parameter substitution in conformance + `(trait, type)` method-table keying, but no new dispatch model. Full multi-impl / argument-overloaded generic traits, trait objects, and user-defined bounds remain deferred. (refines D53) | Adds the generic traits the self-hosted compiler wants without importing argument overloading, which conflicts with name-only method dispatch (D46) |
| D54 | 2026-06-28 | **Re-exports via a `pub`-prefixed import**: `pub` is a uniform prefix modifier on an import statement, marking the name(s) it binds as part of the module's public surface (`pub import a.b.c as c`, `pub from .x import foo`). A `pub import` **requires `as <ident>`** (the export must be a simple identifier — no auto-binding the last path segment, per D22); `from … import name` already binds a simple name. No separate `use` keyword. Re-exports obey the existing collision rules (D22). (resolves the open `pub use` question) | Reuses the existing `pub` visibility modifier as one orthogonal "make this binding public" prefix; avoids a `use` keyword Myla lacks and the last-segment footgun D22 rejected |
| D53 | 2026-06-28 | **Generic trait bounds (limited)**: a type parameter may carry built-in-trait bounds `T: Trait` (`+`-combined); operators/methods named by the bound are usable on `T`, checked at the **call site** during monomorphization (no dynamic dispatch). User-defined trait bounds + trait objects deferred to v0.5. (X9) | Enough for generic numeric/`Eq` code in the self-hosted compiler without a full bounds system |
| D52 | 2026-06-28 | **Operator overloading via a fixed built-in trait set** (`Add/Sub/Mul/Div/Rem/Eq/Ord`): `a OP b` desugars **uniformly** to the trait method, resolving to a user `impl` or the type's built-in implicit default (primitives ship defaults; zero runtime cost when unoverridden). `#derive(Eq)` synthesizes structural equality (allow-list = `Eq` first, then `Ord`); lifts the D37 primitives-only restriction for implementing types. (X8) | Ergonomic operators + structural equality without committing to a broad trait system |
| D51 | 2026-06-28 | **Partial application** `f(…, _, …)`: `_` holes in call-argument position desugar to a lambda over the holes (left-to-right), filled/receiver args captured by value; works on method calls too. **No implicit auto-currying** (a missing non-`_` arg is still an arity error). (X7) | Explicit and loud; keeps arity mistakes from silently becoming partial applications |
| D50 | 2026-06-28 | **`\|>` pipeline + `>>` composition**: `\|>` is a new lowest-precedence, left-associative operator splicing the left value as the **first** argument; `>>` composes when both operands are function-typed, else right-shifts (operand-typed, D24). (X6) | Unambiguous functional plumbing that reuses the existing `>>` token |
| D49 | 2026-06-28 | **Function-value representation**: a 16-byte `(code_ptr, env_ptr)` fat value; `env_ptr` → a refcounted heap cell of captures; non-capturing lambdas & plain `fun`s use `env_ptr = 0`; one calling convention `code_ptr(env_ptr, args…)`. Forward-compatible with `ref` capture (D15) as an additive change (box `ref`-captured locals, store box pointers in the env). (X5) | The OCaml/Rust closure representation; lets `ref` land later without redesign |
| D48 | 2026-06-28 | **Closures capture by value** (snapshot copy at creation, retaining heap captures into the env; mutation affects only the copy). By-reference `ref` capture deferred. (X4, refines D15) | Simple codegen now; clear additive path to `ref` |
| D47 | 2026-06-28 | **Method receivers**: `self` is read-only by value; `var self` mutates and **requires a mutable lvalue receiver** (same rule as `push`/`m[k]=v`, D40) — no mutating calls on temporaries or `let` bindings. (X3, refines D27) | Consistent with the binding-mutability + lvalue rules already in the language |
| D46 | 2026-06-28 | **No UFCS**: methods live in a **per-type namespace**; `recv.method(args)` is the only surface call form (`T::method` is internal lowering). Complementary to the functional operators (method chaining ↔ `\|>`; `_` works on method calls; wrap a method in a lambda to compose). A method-reference value / UFCS may be added later as a non-breaking extension. (X2) | Avoids polluting the value namespace / colliding with builtins (`len`/`push`); the restrictive choice is reversible |
| D45 | 2026-06-28 | **No orphan rule / no origin restriction on `impl`**: any trait (user or built-in) is implementable for any type (user or built-in) — user-on-builtin, builtin-on-user, and builtin-on-builtin all allowed; inherent + trait `impl` allowed on any named type incl. builtins; method names unique per type and distinct from fields; at most one *user* impl per `(Trait, T)`, which **overrides** any built-in implicit default; whole-program coherence. (X1) | Myla is inspired by Rust, not a copy — "simplicity over safety": free mix-and-match, the author takes responsibility |
| D44 | 2026-06-27 | Out-of-range shift amounts: a **constant** amount `>= width` is a compile error; a **runtime** amount is **masked to the operand width** (`n & (width-1)`) rather than trapping (refines the v0.3 "runtime trap" sketch). `<<`/`>>` are parsed as two column-adjacent `<`/`>` tokens, not lexed as single tokens, so nested generic closers (`Option<List<int>>`) keep working. | Masking keeps the interpreter and native backend trivially in parity and matches the hardware shift instructions; the common (constant) mistake is still caught at compile time |
| D43 | 2026-06-27 | Add `0x`/`0b`/`0o` integer literals (with `_` separators + type suffixes) in v0.3. (W6) | Bitmasks and byte/char tables read far better in hex; pairs with the new bitwise ops |
| D42 | 2026-06-27 | v0.3 strings are **byte-oriented**: `s[i] -> uint8`, char literals `'a'`/`'\n'` are their byte code (ASCII only); the dedicated Unicode **`char`** type stays in v0.5. (W5) | What a byte-level lexer needs; keeps Unicode complexity out of v0.3 |
| D41 | 2026-06-27 | `str` `+` concatenation is **allowed** (produces a new immutable `str`); `StringBuilder` is provided for hot loops to avoid O(n²). (W4) | Ergonomic for the compiler's many small concatenations; builder covers the loop case |
| D40 | 2026-06-27 | Mutating collection ops are **in-place on a mutable (`var`) lvalue**: `xs[i] = v`, `push(xs, x)`, `pop`, `insert`/`remove`/`m[k] = v` (built-in intrinsics, since methods arrive in v0.4). (W3) | Extends the lvalue assignment we already have for struct fields; ergonomic |
| D39 | 2026-06-27 | v0.3 ships **list `[T]` + map `[K: V]`**; **sets are deferred** (a set can be a thin map later). (W2) | Lists/maps are what the self-hosted lexer/parser/checker need; sets aren't yet |
| D38 | 2026-06-27 | Lists & maps have **value semantics with copy-on-write** under RC: a copy shares the cell (refcount bump) and any write through a mutable lvalue clones cells with refcount > 1 first; deep immutability (D14) holds. (W1) | Consistent with struct/enum/tuple value semantics, but avoids O(n) copies when threading collections through the compiler |
| D37 | 2026-06-27 | Structural equality is deferred: `==`/`!=` stay **primitives-only** (int/bool/str/char) in v0.2; structs/enums/tuples are compared via `match`. A derivable `Eq` / structural `==` arrives with traits (v0.4). (V8) | Avoids committing equality semantics before traits exist |
| D36 | 2026-06-27 | `?` requires the enclosing function to return the **same carrier** as the operand (Result→Result, Option→Option); no cross-carrier / error-type coercion in v0.2 — traits may generalize it later. (V7) | Simple and explicit; cleaner once traits land |
| D35 | 2026-06-27 | Tuples have **arity ≥ 1**; the 1-tuple is written `(x,)` (type `(T,)`), the trailing comma disambiguating from grouping. **No unit `()` type** yet (void stays "no return type"). (V6) | 1-tuples may be needed; a unit type can come later |
| D34 | 2026-06-27 | Generic type arguments are explicit only in **type positions** (`Option<int>`); at call sites they are **inferred** (no `f<int>(x)` expression syntax, to dodge the `<` ambiguity); annotate the binding if inference is insufficient. (V5) | Avoids turbofish ambiguity; keeps expressions clean |
| D33 | 2026-06-27 | v0.2 `match` pattern set: wildcard `_`, binding, literal (int/bool/str/char), enum variant, tuple, struct, nested, **or-patterns `\|`**, and **guards `if`**; redundant arms are an error. `@`-bindings and range patterns deferred. (V4) | Covers AST-walking needs; room to grow |
| D32 | 2026-06-27 | Enum variant payloads are **positional only** in v0.2 (`Add(Expr, Expr)`); struct-style named-field variants come later. (V3) | Smaller first cut; wrap a struct if names are needed |
| D31 | 2026-06-27 | Variant qualification: construct as **`Enum.Variant(...)`**; `match` patterns may use bare / `.Variant` (scrutinee type is known); the **prelude** exports `Option`/`Result` variants unqualified. (V2) | Explicit construction, ergonomic patterns + common types |
| D30 | 2026-06-27 | **`match` is an expression** (arms are an expression or a block-with-value; also usable as a statement when discarded) — the first value-producing block construct, relaxing the statement-orientation of D1. (V1) | Pattern matching that yields a value is essential for AST-walking code |
| D29 | 2026-06-27 | Freestanding (no-libc) runtime: `std.fs`/`std.io`/`std.process` are thin syscall wrappers (`open`/`read`/`write`/`close`/`exit`, `argv` from `_start`). Process-spawning (driving `as`/`ld` via `fork`/`execve`) is **deferred until after a self-hosted code generator works** — the compiler emits asm and a shell wrapper links it first. (C7) | Honors D2; keeps the hard part (`exec`) off the critical path |
| D28 | 2026-06-27 | Module-level `const NAME: T = <const expr>` only (compile-time constant, file-scoped); **no** top-level mutable/runtime bindings. (C6) | Gives keyword/precedence tables a home without global init-order issues |
| D27 | 2026-06-27 | Mutating methods take a **`var self`** receiver (mirrors `let`/`var`); `recv.method(args)` desugars to `Method(recv, args)` with static dispatch. (C5) | Consistent with the binding-mutability spelling |
| D26 | 2026-06-27 | Explicit numeric conversions via **`x as T`**; narrowing wraps (mod 2^width), widening sign/zero-extends by source signedness, equal-width sign reinterpret is a no-op; shifting by ≥ width is an error. (C4) | Visible, intentional conversions given no implicit mixing (D4) |
| D25 | 2026-06-27 | Add a dedicated **`char`** type (Unicode scalar value) with char literals (`'a'`, `'\n'`); the lexer / string iteration is UTF-8 codepoint-aware; raw byte access stays available via a bytes view. (C3) | UTF-8 correctness in the self-hosted lexer |
| D24 | 2026-06-27 | **`>>` serves both** right-shift and function composition, disambiguated **by operand type** at type-check time (integer operands → shift; function operands → compose); `<<` is left-shift. (C2, refines D8) | Avoids inventing a token; operand context makes intent unambiguous |
| D23 | 2026-06-27 | Self-hosting is the **destination (v1.0)**, reached through feature milestones v0.2–v0.5 + bring-up v0.6–v0.9; retires the old "v0.1 = self-host" framing. (C1) | Self-hosting depends on the post-v0.0 features (see self-hosting.md §2) |
| D22 | 2026-06-27 | Import resolution: leading-dot count selects the search base (no dot = builtins like `std` or project root; `.` = current file's directory; `..` = parent; `...` = grandparent; etc.). Any granularity importable (package/dir, module/file, function, const, struct, trait, ...). `import a.b.c` binds the **full path** `a.b.c`; use `import a.b.c as c` to rebind. `pub` marks exports (private by default). Name collisions are **errors** — resolve with aliases, no automatic resolution. | Explicit and predictable; avoids the footgun of magically binding the last path segment |
| D21 | 2026-06-27 | `str` in v0.0 is **length-prefixed, immutable, UTF-8** (pointer+length), supporting only literals + `print`. `StringBuilder`, string interpolation, views/slices, byte-indexing, and `format` come later (v0.3) | Keeps the bootstrap minimal while guaranteeing a performant, ergonomic string story before self-hosting |
| D20 | 2026-06-27 | Type names use full `intN`/`uintN`/`floatN`; literal suffixes use short `iN`/`uN`/`fN` (e.g. `255u8`, `123i64`, `3f32`) | Readable type names, terse literal disambiguation |
| D19 | 2026-06-27 | Floats are `float32`/`float64`; `float` is an alias for `float32`; literal suffixes `f32`/`f64` (e.g. `1.04f64`, `6f32`) | Mirrors the sized-integer model |
| D18 | 2026-06-27 | Operator overloading via traits to start; fully custom operators postponed to beyond 1.0 | Get things working first; custom operators are a large parser commitment |
| D17 | 2026-06-27 | Python-like imports, explicit only (no wildcards), from builtins or project files | Familiar, explicit (resolution rules later refined in D22) |
| D16 | 2026-06-27 | Error handling via `Result`/`Option` enums + `?` propagation operator (no exceptions) | Fits the ADT direction; explicit error flow |
| D15 | 2026-06-27 | Closures capture by value first; by-reference planned later via a `ref` keyword (e.g. `func(ref a)`) | Simple codegen now, clear path to by-ref |
| D14 | 2026-06-27 | Collections use deep immutability: `let` is immutable in binding and contents; mutation needs `var` | Predictable; safe sharing under reference counting |
| D13 | 2026-06-27 | Generics implemented via monomorphization | Simple native codegen, no boxing, no runtime type tags |
| D12 | 2026-06-27 | Memory model: reference counting first (once we leave all-on-stack) | Simple and predictable; revisit if needed |
| D11 | 2026-06-27 | Integer literals default to `int` (= `int32`); optional type suffixes disambiguate (`255u8`, `123i64`); float suffixes later | Ergonomic default with explicit override |
| D10 | 2026-06-27 | Pull `#main` / `#test(...)[...]` attributes into v0.0 (v0.0.0/0.0.1) so the parser/AST carry attribute metadata from the start; fixed built-in attribute set (not user macros) | Flagged as needed early; cheap if designed in, costly to retrofit |
| D9 | 2026-06-27 | Drop `++`/`--` operators from the core; once custom operators exist (post-1.0), a user may define `++` deliberately | Avoids the prefix/postfix footgun while leaving the door open |
| D8 | 2026-06-27 | Functional style uses `|>` (pipeline), `>>` (composition), `_` partial application; juxtaposition-composition and implicit auto-currying are rejected | Unambiguous grammar, keeps arity errors loud |
| D7 | 2026-06-27 | Primitives are explicitly sized integers (`int8`..`int64`, `uint8`..`uint64`); no dynamic/bignum integers | Fixed widths map to registers/memory; predictable self-hosting |
| D6 | 2026-06-27 | `int` is a built-in transparent type alias for `int32` | Ergonomic default while staying explicitly sized |
| D5 | 2026-06-27 | Support user `typealias Name = Type` (transparent, not new-type) in v0.0 | Cheap; needed to express `int`; improves readability |
| D4 | 2026-06-27 | Integer overflow wraps per operand width; no implicit mixing/widening between integer types | Simple codegen; explicit conversions keep semantics clear |
| D3 | 2026-06-26 | Function keyword is `fun` (not `fn`) | Owner preference |
| D2 | 2026-06-26 | Native backend targets x86-64, emits GAS assembly, links via `as`/`ld`, no libc | Honors no-dependency vision; syscalls cover v0.0 I/O |
| D1 | 2026-06-26 | v0.0 is statically typed, statement-oriented, value-semantics structs, tree-walking interpreter + direct-to-asm compiler | Simplicity; faithful interpreter/compiler parity for self-hosting |

Open decisions (not yet locked) live in
[clarification_needed.md](clarification_needed.md).

---

## How to update this file

- When you start a milestone/feature, flip it to **In progress** and add a `%`.
- When something ships (code + tests + docs), flip it to **Done**.
- When a design choice is settled, add a row to the **Decision log** and remove
  the corresponding entry from `clarification_needed.md`.
