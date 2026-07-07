# Changes from the original Myla

This Rust implementation treats the original Python / self-hosted Myla as
**inspiration, not a spec to clone**. The deliberate differences:

## Fixes for known pain points

1. **Optional semicolons / newline-insensitive parsing.** The original required
   exactly one statement per line. Here a statement ends at a newline *or* `;`,
   with soft continuation rules inside brackets, after trailing operators, and
   before leading `.`/`|>`/`?`. See
   [language-spec.md §4](language-spec.md).

2. **Floats are first-class in every back end.** The original never implemented
   floats in its code generator. Here `float32`/`float64` work in both the
   interpreter and the Cranelift native back end, with round-trippable decimal
   printing (`ryu` in the interpreter, a round-trip C formatter natively), and a
   differential test asserts the two agree.

3. **Unrestricted map/collection keys.** The original assumed scalar-sized keys.
   Here any value — structs, tuples, strings, enums — can be a key, via
   structural `Eq` + `Hash` on the full value.

4. **Rich I/O.** File write/append (not just read), subprocess spawning with
   captured output (`run`), `args`, `env_var`, `now_millis`, `sleep_millis`, and
   stdin (`read_line`) — none of which the original supported.

## New capability

5. **Concurrency** (bonus): Go/Swift-inspired `spawn`/`go`, channels +
   `select`, `async`/`await`, and `actor`s on one runtime. See
   [concurrency.md](concurrency.md).

## Engineering differences

- **Dependencies are embraced.** The original prided itself on *no* dependencies
  (not even libc). This experiment uses `logos` (lexing), `ariadne`/custom carets
  (diagnostics), `ryu` (floats), `ahash` (hashing), `crossbeam`/`parking_lot`
  (concurrency), and **Cranelift** for native code generation instead of
  hand-written x86-64 assembly + a hand-rolled assembler/linker.

- **Native code via Cranelift + the system linker**, not GAS text + a bespoke
  ELF writer. `myla build` emits an object file and links it (with a tiny C
  print runtime) using `cc`.

- **Light static typing.** The original had a dedicated type-checking phase. Here
  `myla-sema` builds symbol tables and checks the high-value compile-time errors
  (mutability, unknown attributes, entry point, duplicate definitions), while the
  interpreter carries runtime types and is the reference semantics. Fuller static
  type inference is a deliberate future extension.

## Scope of the native back end

The interpreter implements the **whole** language. The Cranelift back end
currently lowers the scalar/control-flow/function/print core; anything else
reports a clear `unsupported` message at `build` time (and still runs under
`myla run`). This mirrors the original's reality — where codegen lagged the
interpreter — but with a clean extension path rather than a hard wall.
