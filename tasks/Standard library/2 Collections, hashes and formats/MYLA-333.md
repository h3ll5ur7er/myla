---
id: MYLA-333
title: "std.args: command-line arguments"
type: feature
status: backlog
priority: medium
labels: [stdlib, cli, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #60. A declarative parser: flags, options with values (`--out x`, `--out=x`, `-o x`), positionals, subcommands, defaults, generated `--help`, errors that name the argument.

- **Owns:** `lib/std/args.my`, `docs/Language/Standard-library/Args.md`
- **Needs:** [[MYLA-321]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] The parser and its help text
- [ ] One of the tools in Myla moved to it, as the proof (the smallest one whose parser it replaces)
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
