---
id: MYLA-333
title: "std.args: command-line arguments"
type: feature
status: done
priority: medium
labels: [stdlib, cli, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #60. A declarative parser: flags, options with values (`--out x`, `--out=x`, `-o x`), positionals, subcommands, defaults, generated `--help`, errors that name the argument.

- **Owns:** `lib/std/args.my`, `docs/Language/Standard-library/Args.md`
- **Needs:** [[MYLA-321]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] The parser and its help text
- [x] One of the tools in Myla moved to it, as the proof (the smallest one whose parser it replaces)
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- Page: [[Language/Standard-library/Args]], with a doc block that runs (interpreted and natively the same output).
- Tests first: with the cases written and the bodies stubs (`""`, `None`, `Err(Help(""))`), `myla test lib/std/args.my --stdlib lib` gave 0/23.
- `build/myla test lib/std/args.my --stdlib lib`: 26/26 interpreted, with `--native` and with `--target aarch64-linux` (qemu). On `--target wasm32-wasi` (node) 20/26: the cases run in the harness itself there, and the first expected panic (`undeclared #1`, asking for a name the spec doesn't declare) ends the run, as the wasm32 harness does with any runtime error (no child process can start there); every case before it passes. Cases: 7 on `ArgsError.message`, 3 on the private `find_byte`, 6 expecting the panics of undeclared names, and 10 test functions on positionals and defaults, the long and short forms, grouped flags, repeated options and `many`, `--`, the errors, subcommands, `--help`/`-h`, the help text and the usage line.
- The proof: `tools/embed/main.my` (`embed <lib dir> <module file> [--check]`, the smallest tool, run by `scripts/bootstrap.sh` with stage 0) reads its arguments with `std.args`. Twelve invocations (none, one, two and three arguments, `--check`, an extra positional, `-x`, `--help`, `-h`, `--check=1`, a module that isn't there) give the same stdout, stderr and exit status with the old and the new binary. Only the order is freer: `embed --check lib m` and `embed lib -- m` are accepted now. The seed compiles it, and `scripts/bootstrap.sh` reaches its fixed point. `python3 -m unittest tests.burn.test_embedded_std` OK.
- After `scripts/bootstrap.sh`: `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks` OK.
- Speed, x86-64 natively, best of five: `parse` of 110,002 arguments (a flag, a positional, 100,000 for `many`, 10,000 `-ox`) takes 2.4 ms. Values are kept as one list of (name, value) pairs, so parsing is linear.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-426]]: after `--` a command is still a command; a subcommand's error prints the parent's usage; a spec isn't validated.

The follow-up is done in [[MYLA-426]] (in review, 2026-11-11): after `--` a command's name is an argument, `parse_or_exit` prints the usage of the spec whose arguments were wrong, and a spec that can't be parsed panics where it is built.
