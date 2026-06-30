# Myla Self-Hosting Plan — the road to v1.0

The long-term goal in the [README](../README.md) is for Myla to compile itself.
This document scopes that effort: it works **backwards from the existing v0.0
toolchain** (currently Python, under `src/myla/`) to derive exactly which
language features Myla must grow before its own compiler can be written in Myla.

It is the bridge between [future-features.md](future-features.md) (the catalog of
post-v0.0 features) and [roadmap.md](roadmap.md) (status + milestones): the
features there are not a wishlist, they are the **dependencies of self-hosting**.

Related: [architecture.md](architecture.md) §10 (milestone relationships),
open questions in [clarification_needed.md](clarification_needed.md).

---

## 1. The goal, stated precisely

Re-implement the v0.0 pipeline — lexer → parser → type checker → interpreter →
x86-64 code generator + build driver — in Myla, producing a compiler that can
compile its own source. The Python implementation stays as the **bootstrap
stage 0** and the **reference oracle** for differential testing (§5); it leaves
the critical path only once the Myla compiler reproduces it.

Two properties we must preserve along the way (already true today, and the whole
reason the interpreter and compiler share one typed AST):

- **Interpreter/compiler parity** — same observable behavior either way.
- **No third-party dependencies / no libc** (decisions D1, D2) — the self-hosted
  compiler must also be buildable from just `as` + `ld` and raw syscalls.

---

## 2. Gap analysis — what the toolchain actually uses

Each row maps a current Python module to the Myla feature(s) it would need. This
is what makes the feature list concrete rather than aspirational.

| Module (`src/myla/…`) | What it does | Myla feature(s) required |
|------------------------|--------------|--------------------------|
| `errors.py` | `Position`/error types; render a caret diagnostic; severities | structs ✓; **enums** (severity, error kind); **string building/`format`**; process **exit codes** |
| `tokens.py` | `TokenKind` enum; `Token` record; `KEYWORDS`/`INT_SUFFIXES` tables | **enum** (no-payload variants) or **const** ints; structs ✓; **map**/**set**; module-level **const** |
| `lexer.py` | scan source text char-by-char; build a token list; slice lexemes; classify/compare chars; parse integer literals; keyword lookup | **string indexing + bytes/chars**; **growable list** (+ mutation); **slices**; **comparisons on bytes/chars**; **str→int parsing**; **map** lookup; `break`/`continue` |
| `ast.py` | one record per construct; `Union[...]` node families; optional fields; child lists | structs ✓; **enums / sum types** (or trait objects) for node families; **`Option<T>`**; **`[T]`** lists |
| `parser.py` | recursive descent; indexed token stream; precedence tables; raise on error | recursion ✓; **list** indexing; **const** precedence tables or **map**; **`Result` + `?`**; **`match`** on token/node kind |
| `types.py` | scope tables; type representations; alias/struct/func tables; raise on error | **map** (scopes); **enum** (`Type`); **`Result`/`?`**; recursion ✓ |
| `interpreter.py` | runtime `Value` union; environment; non-local `return`; struct value-copy | **enum** (`Value = Int\|Bool\|Str\|Struct`); **map** (env); control flow for early return (✓ via `return`); value semantics ✓ |
| `compiler/codegen_x86.py` | emit asm text; offset/layout tables; **width wrapping via shifts/masks**; itoa | **`StringBuilder`**; **map**; **bitwise ops** (`& \| ^ ~ << >>`); **numeric casts**; **list** |
| `compiler/__init__.py` | write `.s`; spawn `as` then `ld` | **file write**; **process spawn** (`execve`/`fork`) — the heaviest runtime ask (§4) |
| `cli.py` | parse `argv`; read a `.my` file; print to stdout/stderr; exit codes | **argv**; **file read**; **stderr**; **exit** |

### Features this surfaces that were *not* yet in `future-features.md`

The catalog already covers enums+match, tuples, generics, collections, lambdas,
pipelines, traits/operator-overloading, modules/imports, `Result`/`?`, floats,
and the richer `str` toolkit. The gap analysis adds these **newly-identified**
needs (now written up in [future-features.md](future-features.md) §11–§18):

1. **Bitwise & shift operators** (`& | ^ ~ << >>`) — codegen masks/shifts to wrap
   integers; the lexer/asm layer is bit-twiddly. *(`>>` doubles as right-shift
   and function composition, resolved by operand type — D24.)*
2. **Explicit numeric conversions / casts** — D4 forbids implicit width mixing,
   yet a compiler constantly converts between widths and between bytes/ints/chars.
   An explicit `x as T` cast with defined truncation/sign semantics (D26).
3. **`break` / `continue`** — the scanning/parsing loops need early loop exit.
4. **Characters & string indexing** — lexing reads/compares the units of a
   string; a dedicated `char` (Unicode scalar) type handles UTF-8 (D25).
5. **Methods & `impl` blocks** (beyond operator overloading) — the Python code is
   class-and-method shaped; `recv.method(args)` greatly eases the port. Mutating
   methods take a `var self` receiver (D27).
6. **Module-level `const`** — keyword/precedence tables want compile-time globals
   (v0.0 has no top-level bindings at all); `const` only, no global mutable (D28).
7. **I/O & a freestanding runtime** — file read/write, `argv`, `stderr`, `exit`,
   and (later) process spawning, all via raw syscalls, no libc (D29).
8. **`assert` / `panic` / `unreachable`** — for internal compiler invariants
   (distinct from user-facing `Result` errors).

---

## 3. Minimum viable self-hosting feature set

Grouped into tiers by dependency. A tier generally wants the one above it first.

**Tier A — data modeling** (unblocks porting the AST/types):
- `enum` (sum types, incl. recursive) + exhaustive `match`
- tuples + multiple return + destructuring
- generics (monomorphized): `Option<T>`, `Result<T, E>`

**Tier B — collections & strings** (unblocks the lexer/parser/codegen):
- `[T]` lists with growth + mutation (`var`), `[K: V]` maps, sets
- string length / indexing / slicing / **`char` access (D25)** / comparison
- `StringBuilder` + `format` (avoid O(n²) concat in codegen/diagnostics)
- `str ↔ int` parse/format
- reference counting (D12) — the heap shows up here

**Tier C — operations & glue** (small, fold in with Tier B):
- bitwise/shift operators, numeric casts (`as`)
- `break` / `continue`, module-level `const`
- `assert` / `panic` / `unreachable`

**Tier D — abstraction** (ergonomics for the port):
- methods + `impl` + `self`; traits (incl. operator overloading)
- lambdas/closures + function types; pipelines (`|>`, `>>`/composition)

**Tier E — program structure & runtime**:
- modules / imports (D17, D22) to split the compiler across files
- freestanding runtime: file I/O, `argv`, `stderr`, `exit` (and the `as`/`ld`
  driver question, §4)

**Tier F — bring-up**: port stage-by-stage, validated against Python (§5).

---

## 4. The build-driver question (heaviest runtime dependency)

`compiler/__init__.py` shells out to `as` and `ld`. Porting *that* to Myla means
either spawning processes (`fork`/`execve`) from a no-libc runtime, or keeping a
thin host script outside the language. Proposed staging:

1. The self-hosted compiler **emits assembly to stdout / a file** (pure, easy).
2. A tiny shell/Make wrapper runs `as`/`ld` (keeps process-spawning out of the
   language at first).
3. Later, add a minimal `process`/`exec` syscall wrapper to the stdlib so the
   Myla compiler can drive `as`/`ld` itself and be truly standalone.

This means **self-hosting the front end + codegen does not require process
spawning** — only the final "drive the assembler" convenience does. Good: it
lets us reach a self-hosted *code generator* well before we solve `exec`.

---

## 5. Differential-testing strategy

The Python toolchain is the oracle. As each Myla stage comes up:

- **Lexer**: Myla lexer vs. `myla tokenize` — token kinds/lexemes/positions must
  match on a source corpus (the `examples/` + tests).
- **Parser**: compare a canonical AST dump (`myla parse`) structurally.
- **Checker**: compare accept/reject + diagnostic positions.
- **Interpreter/codegen**: reuse the existing **burn tests** — the Myla-built
  binary must produce the same stdout/exit code as the Python-built one and the
  interpreter, for every example.

Bootstrap validation (the classic three-stage test): once Myla compiles Myla,
build the compiler with stage-0 (Python) → `myla₁`, rebuild with `myla₁` →
`myla₂`, rebuild with `myla₂` → `myla₃`, and assert **`myla₂` and `myla₃` are
byte-identical**. That fixed point is the definition of "self-hosted".

---

## 6. Proposed milestone ordering (reconciliation)

The original roadmap listed *"v0.1 = re-implement v0.0 in Myla"* **before** the
feature milestones — but §2 shows self-hosting **depends on** those features.
Self-hosting is therefore the *destination*, not the next step. Sequence
(locked, D23):

| Milestone | Theme | Delivers (maps to tiers) |
|-----------|-------|--------------------------|
| v0.2 | Data modeling | Tier A: `enum`+`match`, tuples, generics, `Option`/`Result` |
| v0.3 | Collections, strings & ops | Tier B + Tier C: lists/maps/sets, string toolkit, refcounting, bitwise, casts, `break`/`continue`, `const`, `assert` |
| v0.4 | Abstraction | Tier D: methods/`impl`/traits, lambdas/closures, pipelines |
| v0.5 | Modules & runtime | Tier E: imports + stdlib layout, file I/O, `argv`, `stderr`, `exit` |
| v0.6–v0.9 | Self-hosting bring-up | Tier F: port lexer → parser → checker → interpreter → codegen, each differentially tested against Python |
| v1.0 | Self-hosted | Myla compiles Myla; three-stage fixed point reached; Python leaves the critical path |

Incremental self-hosting can start earlier than v0.6: e.g. the **lexer** is
portable as soon as Tier B (strings/lists/maps) exists, so it can serve as the
first real Myla program and validate the feature set before the rest follows.

---

## 7. Decisions (resolved)

The choices this scoping raised are now **locked** as D23–D29 in
[roadmap.md](roadmap.md): milestone numbering — self-hosting is the v1.0
destination (D23); `>>` doubles as shift and composition, resolved by operand
type (D24); a dedicated `char` type for UTF-8 (D25); `x as T` casts with
wrap/extend semantics (D26); `var self` mutating receivers (D27); module-level
`const` only (D28); and a freestanding no-libc syscall runtime with process
spawning deferred (D29).
