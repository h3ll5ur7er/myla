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
```

`myla run` prints `area: 3.5` and `area: 6`; `myla test` runs the `#test` case; `myla build` produces a native binary that prints the same.

[TOC]

## Where to start

| You want to… | Read |
| --- | --- |
| Run your first program, build the compiler, run the tests | [[Getting started]] |
| Learn or look up the language | [[Language]] |
| Understand how the toolchains work inside | [[Architecture]] |
| Change the compiler: tests, bootstrap, conventions | [[Development]] |
| See status, plans, decisions and known problems | [[Project]] |
| Read the original design documents | [[Archive]] |

## The toolchains

The repository holds four implementations of the language and its tools:

| Toolchain | Where | Role |
| --- | --- | --- |
| **Python toolchain** | `src/myla/`, `myla.py` | Bootstrap compiler ("stage 0") and the reference: interpreter, `#test` runner and native x86-64 compiler. See [[Architecture/Lexer-and-parser]] onward. |
| **Self-hosted compiler** | `selfhost/` | The same pipeline written in Myla; compiles itself. See [[Architecture/Self-hosted-compiler]]. |
| **Rust edition** | `rust/` | A separate reimplementation with its own dialect (concurrency, no static checking) and a Cranelift backend. See [[Architecture/Rust-edition]]. |
| **Editor tooling** | `src/myla/lsp/`, `vscode-extension/`, `rust/editor/` | Language server, VS Code extension, tree-sitter grammar. See [[Architecture/Editor-tooling]]. |

```mermaid
flowchart LR
    src[".my source"] --> py["Python toolchain<br/>(stage 0, oracle)"]
    py -->|run / test| out1["program output"]
    py -->|build| bin1["native ELF"]
    py -->|builds| s1["selfhost compiler<br/>(stage 1)"]
    s1 -->|compiles itself| s2["stage 2"] -->|compiles itself| s3["stage 3<br/>= stage 2 byte for byte"]
```

## Status in one paragraph

Version 1.0 is reached: every feature milestone (v0.0 to v0.5) is implemented in the Python toolchain with interpreter/native parity, and the self-hosted compiler reaches its three-stage fixed point. A code review in October 2026 found parity bugs between the interpreter and the native backend, a disabled `free` and several miscompiles in the self-hosted runtime, and a Rust native backend that miscompiles common code. They are tracked as tasks on the board and summarised on [[Project/Known-issues]]. The Python backend's memory and crash bugs from that review are fixed ([[MYLA-2]], [[MYLA-3]], [[MYLA-4]]); the most urgent remaining ones are [[MYLA-21]], [[MYLA-22]] and [[MYLA-36]].

## Working in this repository

- Work is planned as Genbeya tasks in `tasks/` (IDs `MYLA-n`), grouped in epics per component. Name the task in commit messages: `MYLA-12: Encode interpreter strings with surrogateescape`.
- Durable knowledge goes into this wiki, not into private notes. See [[Development/Conventions]].
