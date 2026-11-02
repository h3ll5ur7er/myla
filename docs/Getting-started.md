# Getting started

[TOC]

## Requirements

- **GNU `as` and `ld`** (binutils) on x86-64 Linux: they build the toolchain from its seed, and native programs.
- **Python 3.12 or newer**, only to run the tests (standard library only; `uv` is optional).

## Build the toolchain

```bash
scripts/bootstrap.sh            # output in ./build (gitignored); about 8 seconds
```

This builds the compiler from the committed seed `bootstrap/seed.s` (its own assembly, so only `as` and `ld` are needed), checks that it compiles itself to a byte-identical fixed point, and builds `build/myla`, the command-line tool, and `build/myla-lsp`, the language server. Details, stages and timings: [[Development/Bootstrap]].

## Run a program

```bash
build/myla run examples/hello.my
build/myla run examples/args/main.my a b       # arguments after the file go to the program
```

`run` interprets the program and exits with its exit status (0, or the code passed to `std.process.exit`). A compile error or runtime error prints a diagnostic and exits 1; the carets underline what the error is about:

```
type error: cannot assign to an immutable binding (declare it with 'var')
  --> x.my:3:7
  |
3 |     x = 2
  |     ^^^^^
```

A run reports up to 20 errors: after a syntax error the parser goes on at the next statement or declaration, and once the declarations are consistent every function is checked on its own, reporting its first error. The errors are printed in the order they were found, a blank line apart, followed by `error: aborting due to 3 previous errors`.

## The commands

| Command | What it does |
| --- | --- |
| `myla run <file> [args…]` | Load modules, type-check, interpret |
| `myla test <file>` | Run every `#test(args)[expected]` case; prints `PASS`/`FAIL` per case and exits 1 on a failure |
| `myla build <file> [-o out] [-g]` | Compile to a static x86-64 ELF (`a.out` by default) through `as` and `ld`; `-g` adds DWARF debug information for gdb: line table, variables and types ([[Development/Debugging]]) |
| `myla check <file>` | Type-check only, printing any warnings (D95), then `ok` |
| `myla repl` | The interactive interpreter ([[MYLA-82]]) |

`run`, `test`, `build`, `check` and `repl` take `--package name=dir` (repeatable), before or after the file: a dependency whose modules `import name` and `from name.shapes import …` find in `dir`, as if it were a directory `name/` next to the entry file ([[Language/Modules]]). The project commands below pass these flags themselves. `--stdlib <dir>` names the folder holding `std/`; by default it is `lib` next to the `build/` directory the binary is in, so `build/myla` works from any directory.

The commands live in [[selfhost/main.my]] and [[selfhost/driver.my]]. The REPL:

```text
$ build/myla repl
myla> let xs = [1, 2]
myla> fun twice(n: int) -> int {
...       return n * 2
...   }
myla> twice(len(xs))
4
```

Declarations accumulate, a final expression's value is shown as Myla source writes it, an open bracket continues the input, and an error is reported against the input's lines without ending the session ([[Architecture/Self-hosted-compiler]]).

## Projects

`build/myla` also works on projects: a directory with a manifest `myla.toml`, the program in `src/main.my`, and dependencies on other projects ([[Architecture/Project-tool]], D73). Without a file argument, its commands work on the project around the working directory:

```text
$ build/myla new hello
created package 'hello' in hello/
$ cd hello
$ myla run                 # interpret src/main.my (arguments go to the program)
Hello from hello!
$ myla test                # the #test cases of every file under src/, each file's own
== src/main.my
PASS  greeting #1

1/1 passed in 1 file.
$ myla build               # build/hello (-g: with debug information)
$ myla check               # type-check every file under src/
$ myla clean               # remove build/ (--deps: also .myla/)
```

A dependency on another project by its directory goes into the manifest; its library `src/<name>.my` is then `import <name>`:

```toml
[package]
name = "hello"
version = "0.1.0"

[dependencies]
geo = { path = "../geo" }
```

A dependency from Git names a tag, a branch or a commit (`rev`), or none for the default branch. `myla fetch` resolves it to a commit, checks it out into `.myla/deps/`, and pins it in `myla.lock`, which you commit; the other commands use the pinned commits (checking them out if needed), and `myla fetch --update` moves them:

```toml
[dependencies]
json5 = { git = "https://github.com/example/json5-myla.git", tag = "v1.2.0" }
```

A command given a `.my` file works on that file alone and reads no manifest.

## A first program

```myla
struct Point {
    x: int,
    y: int,
}

#test(Point { x: 3, y: 4 })[7]
fun manhattan(p: Point) -> int {
    var x = p.x
    var y = p.y
    if x < 0 { x = -x }
    if y < 0 { y = -y }
    return x + y
}

fun main() {
    let p = Point { x: 3, y: -4 }
    print(manhattan(p))
    print(f"({p.x}, {p.y})")
}
// output:
// 7
// (3, -4)
```

```bash
build/myla run point.my      # 7, then (3, -4)
build/myla test point.my     # PASS  manhattan #1
build/myla build point.my -o point && ./point
```

Every value-returning function in the examples carries `#test` cases; see [[Development/Conventions]]. The language itself is described in [[Language]].

## The examples, in reading order

Each file in `examples/` is a runnable program with `#test` cases on its functions (`build/myla run examples/<file>`, `build/myla test examples/<file>`):

1. Basics: `hello.my`, `variables.my`, `types_and_aliases.my`, `functions.my`, `control_flow.my`, `loops.my`, `constants.my`
2. Data: `structs.my`, `tuples.my`, `enums.my`, `option-result.my`, `recursion.my`
3. Collections and text: `lists.my`, `maps.my`, `strings.my`, `chars.my`, `unicode.my`, `interpolation.my`, `floats.my`
4. Abstraction: `methods.my`, `closures.my`, `pipelines.my`, `generics.my`, `generic-types.my`, `traits.my`, `traits_on_builtins.my`, `generic_traits.my`, `operators.my`
5. Programs: `attributes.my`, `semicolons.my`, the folders `modules/`, `args/`, `readfile/`, `stdio/` and `subprocess/`
6. Concurrency: `concurrency.my`
7. What the checker rejects: `examples/errors/`, one program per error, its expected message in its first line; and `regressions.my`, the accepted programs that once broke

## Use the compiler directly

```bash
build/stage3 examples/hello.my lib > hello.s
as --64 -o hello.o hello.s && ld -o hello hello.o && ./hello
```

The second argument of the compiler is the folder that contains `std/` (by default `lib` next to its `build/` directory); `build/myla build` does the same in one step. Details: [[Development/Bootstrap]].

## Run the tests

```bash
scripts/test.sh fast        # the quick burn tests, about 20 s once the tools are cached
scripts/test.sh             # all of them (python3 -m unittest discover -s tests/burn -t .), about 2 minutes
```

What each suite guarantees and the current results: [[Development/Testing]].

## Editor support

The VS Code extension in `vscode-extension/myla/` starts the language server written in Myla, `build/myla-lsp` (diagnostics, outline, go to definition, hover, references, completion, semantic highlighting), runs, tests and builds the current file, and debugs it with gdb (`F5`). It finds the tools in the repository's `build/`, so run `scripts/bootstrap.sh` first and open the repository as a workspace folder (or point `myla.compilerPath` at it). Debugging needs gdb: `sudo apt install gdb`.

Install it from a `.vsix`:

- **From CI:** every CI run uploads the extension as the artifact `myla-vscode-extension` (on GitHub: the run's page under *Actions*, *Artifacts*). Unzip the download to get `myla-language-support-<version>.vsix`.
- **Or build it:**

  ```bash
  cd vscode-extension/myla
  npm ci
  npx vsce package          # myla-language-support-<version>.vsix
  ```

Then `code --install-extension myla-language-support-<version>.vsix`, or *Extensions: Install from VSIX…* in VS Code. See [[Architecture/Editor-tooling]] for how it works and [[Development/Debugging]] for debugging.
