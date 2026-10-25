# Rust edition (removed)

From mid-2026 until October 2026 the repository had a second implementation in Rust under `rust/`: a separate dialect and toolchain (logos lexer, Pratt parser, a tree-walking interpreter, a partial Cranelift backend) that shared no code with the Python toolchain or the self-hosted compiler. It was removed in [[MYLA-70]]; the last commit that contains it is `043acb9` (`git show 043acb9:rust/README.md`, or `git checkout 043acb9 -- rust` to bring it back).

[TOC]

## Why it existed

It began as a prototype for a faster **first bootstrap stage**: building the self-hosted compiler with the Python toolchain took over a minute and the first self-built round about four more ([[Project/Roadmap]]). It then also became the testbed for Swift-style actors.

## Why it was removed

- The bootstrap's slowness turned out to be two fixable hot spots in the Python toolchain ([[MYLA-60]], [[MYLA-16]]); the whole bootstrap now takes about 8 seconds ([[Development/Bootstrap]]).
- To serve as a stage 0 it would have had to compile `selfhost/` natively, which needs the full static type system and a native backend for every construct. The dialect had neither: it didn't type-check, and its native backend handled only scalar functions (and silently miscompiled common code).
- Actors are to be designed in the main toolchain with compile-time isolation ([[MYLA-61]], which records what the prototype taught).

## What it was

- **A different dialect**: types parsed but not checked, `float` was `float64`, optional semicolons, any value as a map key, no modules, traits or `#derive`.
- **Concurrency**: `async`/`await`, `spawn`/`go` on OS threads, unbounded `chan` channels with `select`, and `actor` types whose methods ran under a mutex. Its problems (channels that never close, tasks killed at the end of `main`, actors that deadlock calling themselves) are summarised in [[MYLA-61]].
- **More standard library**: `write_file`, `append_file`, `remove_file`, `run`, `env_var`, `now_millis`, `sleep_millis`, `read_line`.

The review's findings about it were tasks [[MYLA-36]] … [[MYLA-46]], closed with the removal.

## What stayed

The tree-sitter grammar that lived in `rust/editor/` moved to `editor/tree-sitter-myla/` ([[Architecture/Editor-tooling]]). It still follows the Rust dialect in places ([[MYLA-47]]).
