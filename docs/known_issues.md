# Known Issues & Limitations

Tracks known gaps in the **self-hosted Myla compiler** (`selfhost/`, reached the
three-stage byte-identical fixpoint — see [roadmap.md](roadmap.md)). The Python
toolchain under `src/myla/` remains the reference oracle; the items below are
places where the self-hosted compiler does **less** than the oracle.

None of these block the bootstrap: the compiler's own source does not use the
unsupported constructs, so `selfhost` still compiles itself to a byte-identical
fixed point.

_Last updated: 2026-06-30._

---

## 1. Floats are not supported by the self-hosted backend

**Status:** known gap · **Severity:** medium · **Blocks bootstrap:** no

`selfhost/codegen.my` has no floating-point code generation: no SSE2/`xmm`
arithmetic, no `cvtsi2sd`/`movsd`, and `gen_print` has no `TFloat` arm (it falls
through the `_ => {}` default and emits nothing). The self-hosted **checker**
accepts float programs without error, so a program that uses `float32`/`float64`
compiles "successfully" but produces wrong or empty output at runtime.

- The Python toolchain fully supports floats (v0.5.2, IEEE-754 SSE2,
  round-trippable decimal `print`/`format`).
- In the example corpus, `examples/floats.my` is the **only** program whose
  self-hosted output diverges from the oracle (it prints the `bool`/`int` lines
  and silently drops every float line).

**Fix sketch:** port the Python backend's float path (`codegen_x86.py`) — `xmm`
register allocation for `TFloat`, SSE2 arithmetic/compare/`as` conversions, and a
`__print_float`/format-float runtime — into `selfhost/codegen.my`, and add the
`TFloat` arm to `gen_print`.

## 2. Map iteration assumes scalar-sized keys

**Status:** latent · **Severity:** low · **Blocks bootstrap:** no

`gen_for_in_map` (in `selfhost/codegen.my`) copies exactly 8 bytes per key into
the loop slot, which is correct for scalar keys (`int*`/`uint*`/`bool`/`char`/
`float` bits) and boxed-enum keys (8-byte pointer), but **wrong for aggregate
keys** (`struct`/`tuple`) whose inline value is larger than 8 bytes — it would
copy only the first word. The analogous list path (`gen_for_in`) was fixed to
dereference boxed elements and copy the full inline payload; the map-key path was
left untouched because it is unexercised: the compiler only ever uses primitive
(`str`/`int`) map keys.

**Fix sketch:** mirror the `gen_for_in` aggregate/boxed handling in
`gen_for_in_map` (copy `size(kt)` bytes, dereferencing the box for boxed keys).

## 3. The self-hosted toolchain is front-end + codegen only

**Status:** by design (D29) · **Severity:** informational

`selfhost/gen_main.my` is a *compile-to-assembly* tool: it lexes → parses →
type-checks → emits x86-64 GAS assembly to stdout. It does **not** include:

- a `build` driver that runs `as`/`ld` itself — process spawning
  (`fork`/`execve`) is deferred until after self-hosting (D29). A host wrapper
  ([`scripts/bootstrap.sh`](../scripts/bootstrap.sh)) runs `as`/`ld`.
- `myla test` / `myla repl` equivalents.

A Myla-language interpreter port (`selfhost/interp.my`) exists but is not on the
bootstrap path.

## 4. Stdlib root must be passed explicitly

**Status:** by design · **Severity:** informational

The self-hosted compiler takes the stdlib root as its second argument
(`gen_main <file.my> <stdlib_root>`, e.g. `src/myla`), because the freestanding
runtime has no notion of an install prefix. The Python toolchain instead uses a
built-in `default_stdlib_root()`. The bootstrap script passes `src/myla`.

## 5. Target is x86-64 Linux only

**Status:** by design (D2) · **Severity:** informational

The only backend is x86-64 GAS/AT&T assembly linked with `as`/`ld` over raw
syscalls (no libc). No other architecture or OS is targeted.

---

## Deferred language features (not bugs)

These are intentionally not implemented yet and are tracked in the
[roadmap decision log](roadmap.md#decision-log-locked-decisions):

- **Sets** — deferred (D39); can be a thin wrapper over a map later.
- **By-reference closure capture (`ref`)** — deferred (D15/D48).
- **Process spawning / package manifest** — deferred (D29).
- **Custom operators, user macros, compound-assignment sugar** — post-1.0.

## Development scratch files

`selfhost/` still contains a few ad-hoc probe drivers used during bring-up
(`probe_check.my`, `probe_chk.my`, `probe_lex.my`, `probe_parse.my`). They are
not part of the toolchain and can be removed once no longer useful.
