# Getting started

[TOC]

## Requirements

- **Python 3.12 or newer.** The Python toolchain has no third-party dependencies; `uv` is optional.
- **GNU `as` and `ld`** (binutils) on x86-64 Linux, for native builds and the bootstrap.
- Optional: **Rust/cargo** for the [[Architecture/Rust-edition]]; **pygls** (`uv sync --extra lsp`) for the language server.

## Run a program

```bash
python3 myla.py run examples/hello.my          # or: uv run myla.py run …
python3 myla.py run examples/args/main.my a b  # arguments after the file go to the program
```

`run` interprets the program and exits with its exit status (0, or the code passed to `std.process.exit`). A compile error or runtime error prints a diagnostic and exits 1:

```
type error: cannot assign to an immutable binding (declare it with 'var')
  --> x.my:3:5
  |
3 |     x = 2
  |     ^
```

## The commands

| Command | What it does |
| --- | --- |
| `myla run <file> [args…]` | Load modules, type-check, interpret |
| `myla test <file>` | Run every `#test(args)[expected]` case; prints `PASS`/`FAIL` per case and exits 1 on a failure |
| `myla build <file> [-o out] [--keep-asm] [-g]` | Compile to a static x86-64 ELF (`a.out` by default) through `as` and `ld`; `-g` adds a DWARF line table for gdb ([[Development/Debugging]]) |
| `myla check <file> [--canonical]` | Type-check only; `--canonical` prints `ok` or `err <line> <col> <kind>` for differential tests |
| `myla tokenize <file> [--canonical]` | Dump the token stream |
| `myla parse <file> [--canonical]` | Dump the AST (`--canonical`: one S-expression per declaration) |
| `myla lsp` | Start the language server on stdio (needs the `lsp` extra) |
| `myla repl` | Not implemented yet ([[MYLA-19]]) |

All commands live in [[src/myla/cli.py]]; `myla.py` only puts `src/` on the import path.

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

The second argument of the self-hosted compiler is the folder that contains `std/` ([[MYLA-31]]). `just bootstrap` does the same and additionally builds `build/myla`, the self-hosted command-line tool with `run`, `test` and `build`. Details, stages and timings: [[Development/Bootstrap]].

## Run the tests

```bash
python3 -m unittest discover -s tests/unit -t .         # ~410 tests, about 1 s
python3 -m unittest discover -s tests/integration -t .
python3 -m unittest discover -s tests/burn -t .         # native builds, about 25 seconds
```

What each suite guarantees and the current results: [[Development/Testing]].

## Editor support

The VS Code extension in `vscode-extension/myla/` starts `python myla.py lsp` and offers diagnostics, outline, go to definition, hover, references and completion. See [[Architecture/Editor-tooling]] for setup and limits.
