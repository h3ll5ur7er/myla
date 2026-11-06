# Bootstrap

"Self-hosted" means: the compiler written in Myla, compiled by itself, produces itself again, byte for byte (D23).

[TOC]

## Stages

The bootstrap starts from a seed: the self-hosted compiler's own assembly for the machine it runs on, committed (D101, [[MYLA-218]]): `bootstrap/seed.s` on x86-64 Linux, `bootstrap/seed-aarch64.s` on aarch64 Linux (D127, [[MYLA-276]]). It needs only that machine's `as` and `ld`. Until the Python toolchain was retired ([[MYLA-219]]), it could build stage 1 instead (`--from-python`); see [[Development/Bootstrap#the-python-toolchains-last-state]].

```mermaid
flowchart LR
    seed["bootstrap/seed.s"] -->|"as + ld"| s0["build/stage0"]
    s0 -->|"compiles selfhost/gen_main.my"| g["build/gen_tool"]
    g -->|"compiles selfhost/gen_main.my"| s2["build/stage2.s → stage2"]
    s2 -->|"compiles selfhost/gen_main.my"| s3["build/stage3.s → stage3"]
    s2 -.->|"cmp: identical"| s3
```

| Stage | What runs | Time (4 cores) |
| --- | --- | --- |
| 0 | `as` + `ld` of `bootstrap/seed.s` into `build/stage0` | 0.7 s |
| 1 | `build/stage0 selfhost/gen_main.my lib > build/gen_tool.s`, then `as` + `ld` | 1.1 s to compile |
| 2 | `build/gen_tool selfhost/gen_main.my lib > build/stage2.s`, then `as` + `ld` | 1.1 s to compile |
| 3 | `build/stage2 selfhost/gen_main.my lib > build/stage3.s`, then `as` + `ld` | 1.1 s to compile |
| check | `cmp build/stage2.s build/stage3.s` | |

A seed older than the sources is an older compiler, which is why the check comes after stage 3: stage 1 is the current compiler as the old one compiled it, stage 2 the first one the current compiler compiled, and `stage2.s` and `stage3.s` are both the current compiler's output. Bootstrapping today's sources from the seed of the commit before [[MYLA-237]] (a code-generation change) reaches the same fixed point, byte for byte.

The result is about 6.2 MB of assembly and a 1.5 MB static binary; the whole script, with `build/myla` and the language server, takes about 7.5 s from the seed (measured on 2026-11-01). A fourth round produces the same output again.

## The seed

`bootstrap/seed.s` is the `stage3.s` of a fixed point, under a header that names the commit it came from and the SHA-256 of the assembly below it. `scripts/update-seed.sh` makes it: it runs the bootstrap from the current seed and writes the new seed. A seed that can no longer compile the sources is updated in steps: an older compiler builds a newer one (Git history), or, as for the first seed, the Python toolchain of `backup/python-toolchain-final` builds stage 1. Git shows it collapsed and without diffs (`.gitattributes`); each new seed adds about 0.6 MB to the repository's history, compressed.

- **When to update it:** once per pull request, in its last commit (D156, [[MYLA-289]]): `scripts/update-seed.sh` (about 8 s), then commit `bootstrap/seed.s`, `bootstrap/seed-aarch64.s` and `selfhost/embedded_std.my`. The commits before it may leave the seeds behind the sources; CI's `bootstrap` job checks the pull request's tip (`scripts/check-seed.sh`) and fails when its seeds aren't the compiler of its sources. The one exception is staging: a new runtime variable or primitive that the standard library is about to use must be in the seed first, so its own commit updates the seed mid-branch. A bootstrap still works from an older seed, as long as it can compile the sources.
- **What a seed costs:** a version adds about 433 KB (x86-64) and 991 KB (aarch64) to the packed history; nothing but the latest seed is needed to bootstrap. In the week before D156 a seed per commit (153 x86-64 and 44 aarch64 versions in six days) made 110 of the pack's 117 MB ([[Project/Review-2026-11]]); one per pull request keeps the chain of seeds, each compiled by the one before, at a small fraction of that.
- **The optional pre-push hook:** `scripts/install-hooks.sh` sets `core.hooksPath` to `.githooks/`, whose `pre-push` runs `scripts/check-seed.sh` (about 6 s) when the commits pushed change `selfhost/`, `lib/std/` or the seed. A stale seed stops a push to `master` or `main`; on another branch it is a reminder, since under D156 only a pull request's last commit has to carry the seed (`MYLA_SKIP_SEED_CHECK=1 git push` skips the check once). It checks the working tree, so commit first.
- **What it doesn't limit:** the seed only has to compile the compiler. What the compiler emits for programs (new system calls, IPC, a C FFI, other backends and platforms) is the compiler's business, not the seed's.
- **The first seed:** commit 74e97c8 (2026-11-01, [[MYLA-218]]) added `bootstrap/seed.s`, the fixed point of the sources at a2f95ba, whose stage 1 the Python toolchain of `backup/python-toolchain-final` (d94f948) built; the SHA-256 of its assembly is `7202f99a1d0031add5c0962830e0d2d5dd5b84a9142b701ee07dc07c7237d045`. Every later seed was compiled by the one before, so the chain goes back to a compiler that wasn't Myla's own.
- **Checking a seed:** run `scripts/update-seed.sh` at the commit its header names and compare; the compiler is deterministic, so the result is the same byte for byte.
- **Other machines** (D127, [[MYLA-276]]): `scripts/bootstrap.sh` (`just bootstrap`) finds the machine with `uname -m` ([[scripts/host.sh]]) and takes its seed: `bootstrap/seed.s` on x86-64, `bootstrap/seed-aarch64.s` on aarch64, such as a Raspberry Pi 4 or 5 with a 64-bit OS or an ARM server. It assembles and links the seed with that machine's GNU `as` and `ld` (binutils; nothing else). The tools it builds target the machine by default (`std.platform.TARGET`, which each target's platform module defines), so `build/myla build x.my` makes an aarch64 program there, through the same `as` and `ld`; another target takes `--target` and clang with lld. 32-bit ARM (`armv7l`) and other systems stop with a message.
- **Both seeds from one machine:** `scripts/update-seed.sh` writes every seed. This machine's is its `stage3.s`; the other's is that compiler's output for the other target, which is what the other machine's fixed point gives, byte for byte, as the compiler is deterministic and behaves the same on every target. `scripts/check-seed.sh` checks both: on one machine it proves that the other machine's seed is this compiler's output for that target, not that the seed is a working compiler there (a miscompile in that target's backend would pass it); CI's `targets` job under qemu and its `bootstrap-arm64` job on hardware prove the rest. CI's `bootstrap-arm64` job runs `just bootstrap` on GitHub's arm64 runner, checks the seeds from there, and compares every example built there with the interpreter.
- **Another machine's bootstrap, emulated:** `MYLA_ARCH=aarch64 AS=aarch64-linux-gnu-as LD=aarch64-linux-gnu-ld MYLA_RUN=qemu-aarch64 scripts/bootstrap.sh build-a64` runs the aarch64 bootstrap on x86-64 (binutils-aarch64-linux-gnu and qemu-user); it reaches the same fixed point in about 75 s.

The burn tests bootstrap from the seed too (`tests/burn/_tools.py`, [[MYLA-235]]), and CI's `bootstrap` job runs without Python, checks that the seed is current, and builds and runs an example with `build/stage3`.

## Why it used to be slow

Until October 2026 the bootstrap took about 5 minutes. Neither slow stage was slow because of Python or because the compiler is big; each had one hot spot:

| Stage | Before | Cause | After |
| --- | --- | --- | --- |
| 1 | about 60 s | 98% in `_collect_list_types`, which re-walked the type graph for every AST node ([[MYLA-60]]) | 3.4 s |
| 2 | about 4 min | the Python backend's allocator scanned one free list on every allocation ([[MYLA-16]]) | 1.3 s |

Both fixes left `stage2.s` byte-identical. A full bootstrap now takes about 8 seconds, so "change the compiler, bootstrap, compare" is an interactive loop.

## Running it

```bash
scripts/bootstrap.sh [OUT_DIR]       # default ./build, from bootstrap/seed.s
scripts/update-seed.sh               # a new seed from the current sources (see "The seed")
scripts/check-seed.sh [build]        # is the seed the current compiler? (CI and the pre-push hook)
scripts/install-hooks.sh             # the optional pre-push hook for this clone
just bootstrap                       # the same
```

After the fixed point, the script also builds `build/myla` (from `selfhost/main.my`), the command-line tool (`run`, `test`, `build`, `check`, `repl`, and the project commands, [[Architecture/Project-tool]]), and `build/myla-lsp` (from `tools/lsp/main.my`), the language server. Its `build` runs `as` and `ld` itself through `std.process.run` and removes the intermediate `.s` and `.o` files; `run` passes the arguments after the file to the program:

```bash
build/myla build examples/hello.my -o build/hello && build/hello
build/myla run examples/args/main.my one two
build/myla test examples/traits.my
```

The tools carry the standard library ([[MYLA-243]]): before stage 1, stage 0 builds `tools/embed/main.my`, which writes `selfhost/embedded_std.my` from `lib/` (each file's text as a string literal) when it changed, so every stage carries the same library and `build/myla` is never older than `lib/` after a bootstrap. The module is committed, so editors see whole sources; `test_embedded_std.py` fails when it isn't what `lib/` gives. `--stdlib <dir>` or `MYLA_STDLIB` name a directory instead (the repository's `lib/` while changing std, without bootstrapping).

## Using the self-hosted compiler directly

```bash
build/stage3 program.my lib > program.s     # the second argument is the folder holding std/
as --64 -o program.o program.s && ld -o program program.o
```

Without the second argument the root is derived from the compiler's location, as for `build/myla`. `scripts/build.sh <file> [out]` wraps this and works from any directory; `build/myla run <file> [args]` interprets a program.

## The Python toolchain's last state

The branch `backup/python-toolchain-final` on GitHub (commit d94f948, 2026-11-01) keeps the last state with the whole Python toolchain as stage 1 and test oracle, before the committed seed ([[MYLA-218]]) and the Python toolchain's retirement ([[MYLA-219]], D101): all suites green, the bootstrap at its fixed point, `MYLA_TEST_BACKEND=python` running the burn tests on the Python backend. To bring the Python toolchain back, start from there (`git checkout backup/python-toolchain-final -- src/myla myla.py`, or a branch from it).

## When the fixed point breaks

The fixed point is a strong check of the self-hosted code generator: any change in `selfhost/` that changes generated code changes `stage2.s`, and stage 3 must reproduce it. If `cmp` fails, the script prints the first differences. Typical causes are output that depends on iteration order, and a code-generation bug that makes the compiler one stage built behave differently from the one the next stage built.
