# Getting started

[TOC]

## Requirements

- **Python 3.12 or newer.** The Python toolchain has no third-party dependencies; `uv` is optional.
- **GNU `as` and `ld`** (binutils) on x86-64 Linux, for native builds and the bootstrap.

## Run a program

```bash
python3 myla.py run examples/hello.my          # or: uv run myla.py run …
python3 myla.py run examples/args/main.my a b  # arguments after the file go to the program
```

`run` interprets the program and exits with its exit status (0, or the code passed to `std.process.exit`). A compile error or runtime error prints a diagnostic and exits 1; the carets underline what the error is about:

```
type error: cannot assign to an immutable binding (declare it with 'var')
  --> x.my:3:7
  |
3 |     x = 2
  |     ^^^^^
```

## The commands

| Command | What it does |
| --- | --- |
| `myla run <file> [args…]` | Load modules, type-check, interpret |
| `myla test <file>` | Run every `#test(args)[expected]` case; prints `PASS`/`FAIL` per case and exits 1 on a failure |
| `myla build <file> [-o out] [--keep-asm] [-g]` | Compile to a static x86-64 ELF (`a.out` by default) through `as` and `ld`; `-g` adds DWARF debug information for gdb: line table, variables and types ([[Development/Debugging]]) |
| `myla check <file> [--canonical]` | Type-check only; `--canonical` prints `ok` or `err <line> <col> <kind>` for differential tests |
| `myla tokenize <file> [--canonical]` | Dump the token stream |
| `myla parse <file> [--canonical]` | Dump the AST (`--canonical`: one S-expression per declaration) |
| `myla repl` | Points to the REPL written in Myla: `build/myla repl` (built by `scripts/bootstrap.sh`, [[MYLA-82]]) |

All commands live in [[src/myla/cli.py]]; `myla.py` only puts `src/` on the import path. The self-hosted CLI, `build/myla` ([[selfhost/main.my]]), has `run`, `test` and `build` (printing what the Python ones print, [[MYLA-81]]) and the REPL:

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
```

```bash
python3 myla.py run point.my      # 7, then (3, -4)
python3 myla.py test point.my     # PASS  manhattan #1
python3 myla.py build point.my -o point && ./point
```

Every value-returning function in the examples carries `#test` cases; see [[Development/Conventions]]. The language itself is described in [[Language]].

## Build the self-hosted compiler

```bash
scripts/bootstrap.sh            # output in ./build (gitignored); about 8 seconds
build/stage3 examples/hello.my src/myla > hello.s
as --64 -o hello.o hello.s && ld -o hello hello.o && ./hello
```

The second argument of the self-hosted compiler is the folder that contains `std/` (by default `src/myla` next to its `build/` directory). The script also builds `build/myla`, the self-hosted command-line tool: `build/myla run|test|build <file.my>`. Details, stages and timings: [[Development/Bootstrap]].

## Run the tests

```bash
python3 -m unittest discover -s tests/unit -t .         # ~410 tests, about 1 s
python3 -m unittest discover -s tests/integration -t .
python3 -m unittest discover -s tests/burn -t .         # native builds, about 30 seconds
```

What each suite guarantees and the current results: [[Development/Testing]].

## Editor support

The VS Code extension in `vscode-extension/myla/` starts the language server written in Myla, `build/myla-lsp` (built by `scripts/bootstrap.sh`), and offers diagnostics, outline, go to definition, hover, references, completion and semantic highlighting. See [[Architecture/Editor-tooling]] for setup and limits.
