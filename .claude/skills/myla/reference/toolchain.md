# Toolchain reference

What `build/myla` and the repository's scripts do, read from the code (`selfhost/main.my`, `driver.my`, `project*.my`, `fetch.my`, `repl.my`, `harness.my`, `test_programs.my`, `interp.my`, `scripts/`, `.github/workflows/ci.yml`). `build/myla --help` prints the usage on stdout (exit 0).

## Commands

The mode is chosen by the arguments, not by the directory: **file mode** when the first argument after the command that isn't an option ends in `.my`, else **project mode** (finds `myla.toml` in the working directory or above; none: `myla: no myla.toml in this directory or above it`, exit 1). `new`, `clean`, `fetch` and `repl` take no file.

| Command | Does |
| --- | --- |
| `myla run f.my [opts] [args…]` | load, check, interpret `main` (or the `#main` function). The program's argv is `[f.my, args…]`. Arguments after the file that aren't `--stdlib`/`--package`/`--root` go to the program, flags included; `--stdlib x` can't be passed to a program |
| `myla test f.my [--only t] [--list] [--native] [--target T]` | the `#test` cases declared **in `f.my` itself** (not in modules it imports) |
| `myla build f.my [-o out] [-g] [--checked] [--target T]` | native binary (default `a.out`); writes `out.s`, `out.o`, runs the assembler and linker, removes both; prints nothing on success |
| `myla check f.my` | type-check; prints `ok` on stdout (warnings on stderr first), exit 0 |
| `myla repl` | interactive interpreter (below) |
| `myla new [--lib] <name>` | creates `<name>/myla.toml`, `.gitignore` (`build/`, `.myla/`), `src/main.my` (a `greeting` function with a `#test` and a `main`) or with `--lib` `src/<name>.my` (a `pub fun greeting`). Name: ASCII letter then letters, digits, `_`; not a keyword, not `std`; directory must not exist |
| `myla build [-g] [--checked] [--target T]` | project: `src/main.my` → `build/<name>` (`-o` is accepted and ignored) |
| `myla run [args…]` | project: interprets `src/main.my` |
| `myla test [--only t] [--list] [--native] [--target T]` | project: every `.my` under `src/` (recursively, sorted, dot-names skipped), then `tests/` (below) |
| `myla check` | project: checks every file under `src/`; prints **nothing** on success (no `ok`) |
| `myla clean [--deps]` | removes `build/` (and `.myla/`); needs only the manifest |
| `myla fetch [--update]` | resolves Git dependencies, checks them out, writes `myla.lock` (`--update`: ignores the lock and re-resolves every one) |

Options valid with every command, before or after the file:

- `--stdlib <dir>`: a directory holding `std/` (default `$MYLA_STDLIB`, else the library compiled into `myla`, whose files errors name `<myla>/std/option.my`). A module of a copy of the library on disk (`myla test lib/std/yaml.my`) is loaded with that copy automatically.
- `--package name=dir` (repeatable): `import name…` resolves in `dir`. The project commands pass these themselves (`name=<dep>/src`).
- `--root <dir>`: the root absolute imports (`from util.strs import f`) resolve in; default the file's directory, `src/` in a project.

`--target T` is `x86_64-linux`, `aarch64-linux` or `wasm32-wasi` (anything else: `myla: unknown target 'T' (…)`, exit 1); the default is the machine's. With `test` it implies `--native`. Tools per target, found on `PATH`: own Linux target `as --64`/`as` + `ld`; the other Linux target `clang --target=<triple>-linux-gnu -c` + `ld.lld -static`; wasm32 `clang --target=wasm32-wasi -mtail-call -mbulk-memory -mnontrapping-fptoint -msign-ext` + `wasm-ld --stack-first -z stack-size=8388608`. A missing tool: `myla: 'clang' was not found: building for aarch64-linux here needs clang and ld.lld`. `-g` is x86-64 only (`myla: -g is not supported for aarch64-linux yet`). Run a wasm module with `node tools/wasm/run.mjs prog.wasm [args…]` (exit code passed on; a trap is `runtime error: …`, exit 1); an aarch64 binary on x86-64 with `qemu-aarch64 ./prog`.

### Exit status and diagnostics

| Status | When |
| --- | --- |
| 0 | success; `myla test` all passed, or no cases (`no #test cases found.`) |
| 1 | any lex/parse/module/type error, a runtime error, a failed test case, `no #test cases match 'x'.`, a failed build step, a project error |
| 2 | no command, unknown command (`myla: unknown command 'x'`), unknown option (`myla: unknown option '-x'`): message then usage on stderr |
| n | `myla run`: the program's `exit(n)`; `myla repl`: an `exit(n)` typed in it |

Diagnostics go to stderr, Rust style (not `file:line:col: …`):

```
type error: cannot assign value of type 'str' to binding of type 'int32'
  --> te.my:2:5
  |
2 |     let x: int = "a"
  |     ^^^^^^^^^^^^^^^^
```

Kinds: `lex error`, `parse error`, `module error` (`cannot read module 'missing.my'`), `type error`, `runtime error`, `manifest error` / `lock file error` (with the `myla.toml` position), `warning[primitive]`, `warning[reentrancy]` (followed by `note:` and `help:` lines; silenced by `#allow(name)` on a function, method or `impl`). Several errors of one stage print a blank line apart, then `error: aborting due to N previous errors`. CLI-level problems are `myla: <message>`. A program without an entry point: `myla run`/`build` fail with `no entry point: define '#main' or a function named 'main'`, `myla check` accepts it. Warnings print on `check`, `run` and `build` alike.

## Testing

### `#test` forms

| Form | Meaning |
| --- | --- |
| `#test(a, b)[v]` | a case: call with `a, b`, compare the result with `v` structurally (maps whatever their order). Several may be stacked; reported `f #1`, `f #2` |
| `#test(a)[v] // label` | named case: `PASS  f #1 (label)` |
| `#test(recv, a)[v]` above a method inside its `impl` | receiver first; reported `T.m #1`, `int32.m`, `[str].m` (only the result of a `var self` method is compared) |
| `#test(a)[panic("msg")]` | passes when the call ends in a runtime error with exactly `msg` |
| `#test(a)[exit(n)]` | passes when the call ends with `exit(n)` (`exit(0)` included) |
| bare `#test` on `fun t()` or `fun t() -> Result<(), E>` | test function: passes on return / `Ok(())`; fails on a runtime error, `exit`, or `Err(e)` (shown as `{}` shows it); reported by name, `PASS  t` |
| `#test…` on an `async fun` | the case runs as the entry task of its own program; children must end; a child's failure fails it |

Not allowed: cases on generic functions, on methods of generic impls or with type parameters, on actor methods and async methods. Arguments are constant-like expressions (literals, constants, struct and enum literals; no local variables). `#test` never affects `run` or `build`.

`std.test` (`import std.test as test`): `expect(cond, msg = "expectation failed")`, `expect_eq(got, want)` (`expected 3, got 4`; `T: Eq + Format`), `expect_ne(got, other)`, `fail(msg)`, `temp_dir()` and `temp_file()` (fresh, under `$TMPDIR` or `/tmp`, removed when the case ends; outside `myla test` a runtime error), `program()` (the project's built program; elsewhere the runtime error `test.program() needs a project with a program: run 'myla test' in it`). Every failure is a runtime error.

```myla
import std.test as test
import std.fs as fs
from std.process import exit

#test(1, 2)[3] // small numbers
#test(-1, 1)[0]
fun add(a: int, b: int) -> int {
    return a + b
}

#test(0)[panic("division by zero")]
#test(1)[exit(3)]
#test(2)[5]
fun tenth(n: int) -> int {
    if n == 1 { exit(3) }
    return 10 / n
}

struct Counter { n: int }

impl Counter {
    #test(Counter { n: 2 }, 3)[5]
    fun plus(self, k: int) -> int {
        return self.n + k
    }
}

#test
fun scratch_dir_is_fresh() -> Result<(), fs.IoError> {
    let d = test.temp_dir()
    fs.write_to_file(d + "/a.txt", "hi")?
    test.expect_eq(fs.read_to_string(d + "/a.txt")?, "hi")
    return Ok(())
}

#test(5)[25]
async fun square(n: int) -> int {
    return n * n
}

fun main() {
    print(add(1, 2))
}
// output:
// 3
```

### Running

- Report, after what the cases printed themselves: `PASS  add #1 (small numbers)`, `FAIL  add #2: expected 5, got 4`, `FAIL  f #1: runtime error: <msg>`, `FAIL  f #1: exited with status 3`, `FAIL  f #1: expected runtime error 'm', got 2`; a failed case's own stdout follows under it as `      | line` (a passing case's isn't shown); then a blank line and `6/8 passed.` (project: `5/5 passed in 5 files.`).
- `--only <text>`: the cases whose **function name** contains the text (`T.m` for a method; not the label, not `#2`); in a project also test programs whose path contains it. `--list`: prints the case names (`add #1 (small numbers)`), runs nothing, exit 0.
- Interpreted (`myla test`): a failure ends that case only; its deferred blocks run (a failing one adds `; deferred block: runtime error: …`); integer overflow always traps. `MYLA_SCHED`/`MYLA_TIME` are not read: tasks run in the default order.
- `--native` / `--target T`: builds a harness (`selfhost/harness.my`: the file's text, `main`/`#main` blanked, plus a case dispatcher and a `#main` calling `std.test`'s runner) **checked**, in `$TMPDIR/myla-test-<ns>/`, runs every case in a child process of itself; same report. Differences: a failed case runs no deferred block; a function value shows as `<function>`. Other targets run under `$MYLA_EMULATOR` (split on spaces) else `qemu-aarch64` for aarch64; **wasm32 has no default**: `MYLA_EMULATOR="node tools/wasm/run.mjs" myla test f.my --target wasm32-wasi` (without it: `myla: cannot run the test harness with '…/harness'`). On wasm32 (no processes) the harness runs `--from <k>` repeatedly. A harness that doesn't build is kept as `…/harness.my`. A file whose function calls `main` doesn't build as a harness.

### Projects

`myla test` in a project: (1) if `tests/` exists and the project has `src/main.my`, it first builds the program **checked** to `build/<name>` (`test.program()`); (2) each file under `src/`, then each non-program file under `tests/`, runs its own cases, a `== src/x.my` block per file that has any; (3) test programs under `tests/` under `== tests/`, `PASS  tests/echo.my`. Dependencies' cases don't run. A file that doesn't compile: its error, then `myla: N files not compiled`, exit 1.

A **test program** is a file whose trailing `//` comment block contains a line `// output:`; sections in any order, each line is the text after `// ` (or `//`):

| Directive | Meaning (default) |
| --- | --- |
| `// output:` | exact stdout (required; makes the file a test program) |
| `// input:` | stdin (empty) |
| `// exit: n` | exit status (0) |
| `// stderr:` | stderr must **start** with these lines (not compared) |

It runs through `myla run <file> --root src …` (or built, with `--native`). Failures: `FAIL  tests/x.my: output differs` with `expected:`/`got:` blocks, `exited with status 1, expected 0`, `stderr differs`, `killed by signal 9, …`.

```myla fragment
// tests/fails_cleanly.my
from std.io import stdin

fun main() {
    var r = stdin()
    match r.read_line() {
        Ok(Some(l)) => { print("got " + l) },
        _ => {},
    }
    panic("bad")
}
// input:
// zz
// output:
// got zz
// exit: 1
// stderr:
// runtime error: bad
```

## `myla.toml`, `myla.lock`

```toml
[package]
name = "app"            # required; the package-name rules of `myla new`
version = "0.1.0"       # required string
description = "…"       # optional string
license = "MIT"         # optional string
authors = ["A <a@b>"]   # optional array of strings

[dependencies]
shapes = { path = "../shapes" }                                  # relative to this manifest
geo = { git = "https://example.org/geo.git", tag = "v1.2" }      # or branch = "main", or rev = "<40 hex>", or none: default branch
```

- Only `[package]` and `[dependencies]` at the top; any other key is a `manifest error: unknown key …` with its position. A dependency is a table with exactly one of `path`/`git`, at most one of `tag`/`branch`/`rev` (only with `git`); `shapes = "1.0"` is an error.
- A dependency must have `myla.toml` whose `name` equals its key, and a library `src/<name>.my`; it is imported as `import shapes` (`shapes.greeting(…)`) or `from shapes import greeting`, and its other modules as `from shapes.util import …`. One version per name across the graph (`two versions of package 'x': …`).
- Layout: `src/main.my` (program), `src/<name>.my` (library), `tests/`, `build/` (output), `.myla/deps/<name>-<commit>/` (Git checkouts, never changed afterwards; cloned into `….partial`, then renamed).
- Git: `git` on `PATH`, `GIT_TERMINAL_PROMPT=0`. A Git dependency with no current lock entry is an error for every command but `fetch` (`dependency 'geo' is not locked: run `myla fetch``); a locked commit not checked out yet is checked out by `build`/`run`/`test`/`check` (`fetching geo tag v1.2 (0c296e7)` on stderr).
- `myla.lock` (written by `fetch`, commit it): `# Written by `myla fetch`. Commit it; don't edit it.`, `version = 1`, then per package `[git.<name>]` with `url`, the `tag`/`branch`/`rev` asked for, and `commit` (40 hex).

## REPL (`myla repl [--stdlib d] [--package n=d]`)

- Prompts `myla> ` and `...   ` on stderr; values and output on stdout. An input continues while a bracket is open.
- An input starting with `fun`, `struct`, `enum`, `impl`, `trait`, `const`, `typealias`, `import`, `from`, `pub` or `#` is a declaration and joins the session; anything else is statements, run once in a scope holding earlier variables (a later `let` may shadow). A final expression's value is shown as source (`"hi"`, `[1, 2]`, `Some(1.5)`, `P { x: 1 }`); `let` shows nothing.
- `actor` and `async fun` can't be declared (they parse as statements: `parse error: expected an expression, found 'actor'`).
- No `:commands`. End: Ctrl-D on an empty line (or end of piped input), status 0; `exit(n)` ends with `n`. On a terminal: line editing and history (std.term); Ctrl-C drops the current input. Errors are reported against `<input>:line:col` and leave the session unchanged.

## Environment variables

| Variable | Read by | Effect |
| --- | --- | --- |
| `MYLA_STDLIB` | all tools, LSP | directory holding `std/` (like `--stdlib`); a missing one is a module error |
| `MYLA_THREADS` | native binaries | worker count; default the CPUs the process may use; clamped to 1..32; ignored on wasm32 and by the interpreter |
| `MYLA_SCHED` | `myla run`, native binaries | ready-task order: default newest first; `fifo` oldest first; `seed:N` pseudo-random end per task; exact spelling (`Fifo` is the default). Not read by `myla test` |
| `MYLA_TIME=virtual` | `myla run` only | the interpreter's monotonic clock jumps to the next deadline when no task is ready (sleeps cost nothing); wall clock unaffected |
| `MYLA_LOG` | `std.log` | `error`, `warn` (default, also for unknown values), `info`, `debug`, `off`; any case |
| `MYLA_EMULATOR` | `myla test --target` | the command the harness and test programs run under (`node tools/wasm/run.mjs`) |
| `MYLA_TEST_PROGRAM`, `MYLA_TEST_DIR`, `MYLA_TEST_EMULATOR` | set by `myla test` for harnesses | `test.program()`, the scratch root, the emulator for child cases |
| `TMPDIR` | `myla test`, `std.test` | scratch root (default `/tmp`) |
| `MYLA_ARCH`, `AS`, `LD`, `MYLA_RUN` | `scripts/host.sh` | bootstrap another machine's seed here (arch, binutils, emulator to run stages under) |
| `MYLA` | `scripts/build-page.sh` | the compiler to use (default `build/myla`) |
| `PYTHON` | `scripts/test.sh` | interpreter (default `python3`) |
| `MYLA_REQUIRE_TARGETS=1`, `MYLA_REQUIRE_BROWSER=1` | burn tests | fail instead of skip when clang/lld/qemu or Playwright are missing (CI sets them) |
| `MYLA_TEST_TARGET` | burn tests | the target `scripts/test-target.py` runs a suite for |
| `MYLA_PIN_DIAGNOSTICS=1` | `test_error_corpus` | writes missing `examples/errors/*.stderr` pins |
| `MYLA_GENERATED=full`, `MYLA_GENERATED_SEED` | generated burn suites | all cases / another seed |

## Runtime semantics a program author meets

- **Interpreter vs native.** Same stdout and exit status (CI and the doc-block test compare them). Differences: a runtime error in the interpreter shows the source line and carets, natively only `runtime error: <msg>` and `  --> file:line:col`; the interpreter's call depth stops at **2500** calls (`runtime error: stack overflow`, no position) where native code has a 120 MiB main stack (100000-deep recursion is fine natively, `become` avoids the limit in both); overflow traps in `run`/`test`/`build --checked` and wraps in a plain `build`, where a too-large shift count is masked; native tasks run in parallel on several workers, the interpreter one at a time; raw-memory primitives are native-only (`'__load64' reads and writes raw memory, which only native code does`).
- **Task order** (interpreter, and native on one worker, identical): `async let` doesn't start the child; children run when the parent suspends (`await`), newest ready first, depth first; `await task.yield()` goes behind the others. A failure in any task reports at once and ends the program (exit 1). All tasks blocked: `runtime error: every task waits for another one`.
- **Runtime error texts** (the same natively, `[panic("…")]` matches them exactly):

| Text | Cause |
| --- | --- |
| `integer overflow` | `+ - *`, unary `-`, `MIN / -1` (checked modes) |
| `shift amount out of range` | shift count ≥ width or negative (checked modes) |
| `division by zero`, `modulo by zero` | integer `/`, `%` by 0 |
| `list index 5 out of bounds (len 3)` | also `-1`; a byte list too |
| `string index 5 out of bounds (len 2)` | `s[i]` |
| `map key 'b' not found` | `m[k]` read; key written as a value (`'b'`, `3`, `P { x: 1 }`) |
| `pop from an empty list` | `xs.pop()` |
| `slice step is zero` | `xs[::0]` |
| `a slice bound inside a character` | `s[a:b]` splitting a UTF-8 character |
| `string range 0..5 out of bounds (len 2)` | `sb.append(s, start, end)` |
| `invalid char: 1114112 is not a Unicode scalar value` | `c + n` past a scalar |
| `assertion failed` / the message | `assert(c)` / `assert(c, msg)` |
| the message | `panic(msg)`, `opt.expect(msg)`, `res.expect(msg)` (position inside `<myla>/std/option.my`) |
| `reached unreachable code` | `unreachable()` |
| `stack overflow` | deep recursion (no position) |
| `use of a closed notifier` | a `task.notifier()` after `close()` |
| `every task waits for another one` | deadlock |
| `no entry point: define '#main' or a function named 'main'` | `run` without `main` |

A literal format spec in `format`/an f-string is checked at compile time (`type error: invalid format spec 'zz'`); only `x.format(spec)` with a computed spec fails at run time, in `std.fmt`.

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/bootstrap.sh [OUT=build]` | stage0 = the machine's seed (`bootstrap/seed.s` x86-64, `seed-aarch64.s` aarch64) assembled; **embed**: stage0 builds `tools/embed` which rewrites `selfhost/embedded_std.my` from `lib/` if it changed (a tracked file: commit it); stage1 `gen_tool` = stage0 compiling `selfhost/gen_main.my`; stage2, stage3; asserts `stage2.s == stage3.s` byte for byte; stage3 builds `build/myla` (from `selfhost/main.my`) and `build/myla-lsp`; smoke-tests a type error (exit 1) and an LSP initialize/shutdown. Linux only; needs `as`, `ld`; ~8 s |
| `scripts/update-seed.sh` | bootstraps into `build/seed-update`, checks the eight implicit modules whole (`myla check lib/std/<m>.my --stdlib lib`), writes both seeds (stage3's output per target, built with an empty embedded library, with a header naming the commit and a sha256). Ends every PR that changes `selfhost/` or `lib/std/` (D156) |
| `scripts/check-seed.sh [BUILD]` | exit 0 when both seeds are the current compiler; 1 when stale or when `selfhost/embedded_std.my` differs from HEAD; 2 on a failed bootstrap. CI and the pre-push hook run it |
| `scripts/host.sh` | sourced: host target, seed, `asm_to_bin`, `run_tool`, `seed_compile` |
| `scripts/test.sh [fast\|all]` | burn tests via `python3 -m unittest`; `fast` drops `test_selfhost_*` and ~25 slow modules |
| `scripts/test-target.py T [MODULE…] [-j N]` | burn suites for `aarch64-linux` (qemu) or `wasm32-wasi` (Node), exceptions in `tests/burn/_targets.py` |
| `scripts/stress-native.py [--runs N] [--workers 1,4,16] [--only t…]` | concurrency stress programs natively |
| `scripts/build.sh f.my [out]` | `build/stage3 f.my lib` piped to `as`/`ld` (stage3 directly) |
| `scripts/build-page.sh [OUT=build/page]` | the wasm playground: `play.wasm` + `tools/wasm/{page.html,myla.mjs,wasi.mjs,mem_fs.mjs}` |
| `scripts/gen_treesitter.sh` | `editor/tree-sitter-myla` from `grammar/myla.ebnf` |
| `scripts/gen_std_int.py [--check]` | generates `lib/std/int.my` (don't edit it by hand) |
| `scripts/gen_unicode_tables.py` | `selfhost/unicode.my` identifier tables |
| `scripts/test_coverage.py [DIR]` | share of value-returning functions with `#test` (target 80 %) |
| `scripts/to_methods.py FILE…` | rewrites `push(xs, v)`-style calls to methods |
| `scripts/install-hooks.sh` | `core.hooksPath = .githooks` (pre-push runs check-seed) |

`justfile`: `just bootstrap`, `just build <src> <out>`, `just run <src> [args]`, `just test <src>`, `just run-all <dir>` (build and run every `.my` there).

The compiler itself: `build/stage3 <file.my> <stdlib-dir> [--target T] [-g] [--checked] [--emit-ir] [--package n=d] [--root d]` writes assembly to stdout (`selfhost/gen_main.my`). Other entry points, for the burn tests: `lex_main`, `parse_main` (`--lazy`), `check_main`, `interp_main`, `project_main`, `floatlit_main`, `play_main` (`play check|run|test`, the wasm playground's toolchain; `check` prints diagnostics as JSON).

## CI (`.github/workflows/ci.yml`, on push to master and PRs)

| Job | Runs |
| --- | --- |
| `burn` | the whole burn suite with gdb, clang, lld, qemu-user, Node, Go and tree-sitter, `MYLA_REQUIRE_TARGETS=1` |
| `targets` (aarch64-linux, wasm32-wasi) | `scripts/test-target.py <target>` |
| `wasm-page` | the playground page in Chromium (Playwright) |
| `bootstrap` | `scripts/bootstrap.sh build`, `scripts/check-seed.sh build`, stage3 builds `examples/hello.my` |
| `bootstrap-arm64` | `just bootstrap` on arm64, check-seed, every example built vs interpreted, stress runs |
| `vscode-extension` | typecheck, lint, tests (debugger against gdb), `.vsix` |

## `tools/`

| Tool | What | Built / run |
| --- | --- | --- |
| `tools/lsp/` | language server (stdin/stdout LSP): diagnostics, document symbols, definition, hover, references, completion, semantic tokens; projects resolved with their packages. `--stdlib d`; `--resolve f…` prints what each identifier refers to | `build/myla-lsp` by `bootstrap.sh`; used by `vscode-extension/myla` |
| `tools/embed/` | `embed <lib dir> <module> [--check]`: writes `selfhost/embedded_std.my` (library text plus pre-parsed declarations) | by `bootstrap.sh` |
| `tools/grammar/` | `grammar canon <file>`, `grammar treesitter <ebnf> <highlights> <dir>`, `grammar sample <ebnf> <seed> <n> [parse]` | `build/myla build tools/grammar/main.my -o build/grammar` |
| `tools/wasm/` | `run.mjs` (Node WASI runner, `--argv0 NAME`), `wasi.mjs`, `node_fs.mjs`, `mem_fs.mjs`, `myla.mjs` (`loadMyla(...)` → `check`, `run`, `test` in a page), `page.html` | JavaScript, no build; `scripts/build-page.sh` |

There is **no formatter** and no `myla fmt`; the tree-sitter grammar is `editor/tree-sitter-myla`, the VS Code extension `vscode-extension/myla` (runs, tests, builds, debugs with gdb).

## Repository test conventions (`tests/burn/`)

- Python `unittest`: `python3 -m unittest tests.burn.test_error_corpus -v` for one module; `scripts/test.sh fast|all`. The tests build their own tools from the seed into `build/test-tools/` (cached by a hash of `lib/std/*.my`, `selfhost/*.my`, `tools/**/*.my`, `bootstrap/seed.s`) and pass `--stdlib lib`: they test the working tree without a bootstrap, but `build/myla` needs `scripts/bootstrap.sh` to see changes.
- **Examples** (`examples/*.my`): add the expected stdout to `EXPECTED` in `test_examples_run.py` and the name to `EXAMPLES` in `test_examples_compile.py` (both tests fail when the lists and the directory differ); every value-returning top-level function needs a `#test` (`test_examples_tests.py`), and all cases must pass.
- **Error corpus** (`examples/errors/*.my`): one line `//~ <lex|parse|module|type|runtime> error: <substring>` anywhere in the file; optional `//~ span: <underlined text>`, `//~ errors: N` with `//~ next: <substring>` per later error, `//~ note: …`, `//~ help: …`, `//~ note span: …`. A runtime-error file also needs `//~ native: runtime error: <exact native line>` and, for an overflow, `//~ checked`. A file without a recording from the retired Python toolchain needs `<name>.stderr` beside it, the whole rendered diagnostic (`MYLA_PIN_DIAGNOSTICS=1` writes it; review it).
- **Doc blocks** (`test_doc_blocks.py`): every ```` ```myla ```` block in `docs/**/*.md`, `README.md` and `.claude/skills/myla/**/*.md` is written to `main.my` in an empty temp dir and must `check`; with `fun main(` it must `run` with exit 0 (stdin empty) and build natively with the same stdout; an optional trailing `// output:` section gives the exact stdout (`//` alone = an empty line). ```` ```myla fragment ```` is skipped, ```` ```myla error ```` must fail to check. `.claude/skills/myla/` and `.agents/skills/myla/` must hold the same files.
