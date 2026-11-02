# Home

Myla is a small, statically typed programming language with sized integers, value semantics, algebraic data types, traits and closures. It is inspired by Swift, Rust and Python. It compiles to x86-64 Linux executables without libc, and it is **self-hosted**: the compiler written in Myla compiles itself to a byte-identical fixed point.

```myla
enum Shape {
    Circle(float64),
    Rect(float64, float64),
}

#test(Shape.Rect(2.0, 3.0))[6.0]
fun area(s: Shape) -> float64 {
    return match s {
        Circle(r) => 3.5 * r * r
        Rect(w, h) => w * h
    }
}

fun main() {
    let shapes = [Shape.Circle(1.0), Shape.Rect(2.0, 3.0)]
    for s in shapes {
        print(f"area: {area(s)}")
    }
}
// output:
// area: 3.5
// area: 6
```

`myla run` prints `area: 3.5` and `area: 6`; `myla test` runs the `#test` case; `myla build` produces a native binary that prints the same.

[TOC]

## Where to start

| You want to… | Read |
| --- | --- |
| Run your first program, build the compiler, run the tests | [[Getting started]] |
| Learn or look up the language | [[Language]] |
| Understand how the toolchain works inside | [[Architecture]] |
| Change the compiler: tests, bootstrap, conventions | [[Development]] |
| See status, plans, decisions and known problems | [[Project]] |
| Read the original design documents | [[Archive]] |

## The toolchain

| Part | Where | Role |
| --- | --- | --- |
| **Self-hosted toolchain** | `selfhost/`, `lib/`, `bootstrap/seed.s` | The compiler, interpreter, `#test` runner, REPL and project tool, written in Myla; `build/myla` runs and builds programs. It compiles itself, starting from a committed seed, its own assembly. See [[Architecture/Self-hosted-compiler]] and [[Development/Bootstrap]]. |
| **Editor tooling** | `tools/lsp/`, `vscode-extension/`, `editor/`, `grammar/`, `tools/` | Language server (written in Myla), VS Code extension (with a gdb debugger), the grammar description and the tree-sitter grammar generated from it by a tool written in Myla. See [[Architecture/Editor-tooling]]. |

Until November 2026 a Python toolchain (`src/myla/`, `myla.py`) was the bootstrap and the reference the self-hosted one was tested against; it was retired by D101 ([[MYLA-219]]), and the tests now compare with its answers, recorded ([[Development/Testing]]).

```mermaid
flowchart LR
    seed["bootstrap/seed.s"] -->|"as + ld"| s0["stage 0"]
    s0 -->|compiles selfhost/| s1["stage 1"]
    s1 -->|compiles itself| s2["stage 2"] -->|compiles itself| s3["stage 3<br/>= stage 2 byte for byte"]
    s3 -->|builds| cli["build/myla"]
    cli -->|run / test| out1["program output"]
    cli -->|build| bin1["native ELF"]
```

## Status in one paragraph

Version 1.0 is reached and well past: every feature milestone was implemented with interpreter/native parity, and the self-hosted compiler reaches its three-stage fixed point. Since then the self-hosted backend goes through a verified mid-level IR ([[Architecture/IR]]), with guaranteed tail calls (`become`, D87); the language has Swift-style concurrency (D89 to D97: `async`/`await`, structured child tasks, actors) on a multi-threaded work-stealing native runtime ([[Language/Concurrency]]); and the tools are written in Myla: a project tool with Git dependencies ([[Architecture/Project-tool]]), a language server and a REPL, beside a VS Code extension with a debugger ([[Architecture/Editor-tooling]]). In November 2026 the bootstrap moved to a committed seed and the Python toolchain was retired (D101). The review of October 2026 ([[Project/Review-2026-10]]) found the bugs now on the board and on [[Project/Known-issues]]; next is LLVM and other platforms ([[MYLA-62]]).

## Working in this repository

- Work is planned as Genbeya tasks in `tasks/` (IDs `MYLA-n`), grouped in epics per component. Name the task in commit messages: `MYLA-12: Encode interpreter strings with surrogateescape`.
- Durable knowledge goes into this wiki, not into private notes. See [[Development/Conventions]].
