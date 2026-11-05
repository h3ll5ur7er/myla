---
id: MYLA-276
title: "Bootstrap on the machine it runs on: `just bootstrap` on a Raspberry Pi, the machine the default target"
type: feature
status: review
priority: high
labels: [bootstrap, platforms, aarch64, ci]
---
The owner's request (2026-11-04): clone the repository on a Raspberry Pi 4, run `just bootstrap` and start coding in Myla. The bootstrap recognises the machine and builds for it, and afterwards nothing needs extra command-line arguments. Decided as D127.

- [x] A seed per machine: `bootstrap/seed-aarch64.s` beside `bootstrap/seed.s` (x86-64), both written by `scripts/update-seed.sh` from either machine and checked by `scripts/check-seed.sh`
- [x] `scripts/bootstrap.sh` (`just bootstrap`) finds the machine (`uname -m`, [[scripts/host.sh]]), takes its seed and assembles and links with its own GNU `as` and `ld`; 32-bit ARM and other systems stop with a message saying why
- [x] The compiler's default target is the one it was built for (`std.platform.TARGET` in each target's platform module): `myla build`, the project commands and `gen_main` build for the machine without `--target`
- [x] Its own target through `as` and `ld`, another through clang and lld (`build_commands` in [[selfhost/driver.my]]); a missing tool named, with what the target needs (`missing_tool`)
- [x] CI: `bootstrap-arm64` on GitHub's arm64 runner runs `just bootstrap`, checks the seeds and compares every example built there with the interpreter
- [x] [[Development/Bootstrap]], [[Getting started]], the README, AGENTS.md and the `myla` skill

## How it works

- **The seeds.** Each is the compiler at its fixed point as its machine's assembly. The aarch64 one is the x86-64 compiler's output for `--target aarch64-linux`. That is exactly what the aarch64 compiler gives when it compiles itself, because the compiler is deterministic and behaves the same on every target.
- **The scripts.** [[scripts/host.sh]] is sourced by the three seed scripts. Overrides let an x86-64 machine run the aarch64 bootstrap under emulation: `MYLA_ARCH`, `AS`, `LD`, `MYLA_RUN`.
- **The default target.** `myla` and `gen_main` import `std.platform.TARGET`. The loader swaps each target's platform module in for `std/platform.my`, so the constant is the target the tool itself was built for.

## Evidence (2026-11-04)

- **The aarch64 bootstrap**, emulated with aarch64 binutils and qemu:
  - `MYLA_ARCH=aarch64 AS=aarch64-linux-gnu-as LD=aarch64-linux-gnu-ld MYLA_RUN=qemu-aarch64 scripts/bootstrap.sh` builds stages 0–3 from `bootstrap/seed-aarch64.s` and reaches the byte-identical fixed point (19,080,213 bytes);
  - it builds `myla` and `myla-lsp` and passes the CLI's and the language server's checks, in 75 s;
  - the embedded standard library is unchanged by it.
- **GNU binutils** (what a Pi has) assemble and link the aarch64 backend's output, which until now only clang had: the GNU-built aarch64 compiler compiles `examples/maps.my` to the same assembly as the x86-64 one.
- **The aarch64 `myla`**, under qemu with `as` and `ld` pointing at the aarch64 binutils:
  - with no `--target` it builds every example for aarch64, and each gives what `myla run` gives;
  - its usage names `aarch64-linux` as the default.
- **Determinism:** `scripts/check-seed.sh` run as the aarch64 machine finds `bootstrap/seed.s`, the x86-64 seed, equal to what the aarch64 compiler writes for x86-64, byte for byte. Run as the x86-64 machine it finds both seeds current.
- **`build_commands`' and `missing_tool`'s `#test` cases** pass (six).

## Not done

- The test suites (`tests/burn`) still assume an x86-64 machine (`_tools.py` assembles with `as --64`). On an aarch64 machine the bootstrap and `myla` work, but `scripts/test.sh` doesn't yet; that is [[MYLA-268]]'s.
- `-g` stays x86-64's ([[MYLA-259]]).
