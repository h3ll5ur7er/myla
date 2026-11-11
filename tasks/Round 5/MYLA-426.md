---
id: MYLA-426
title: "P12 Terminal, paths, arguments, platform corners, small modules"
type: bug
status: in-progress
priority: medium
labels: [std, term, glob, args, platform, round-5]
---
Work package P12 of [[Project/Review-2026-11-09]] (wave A2). Files: `lib/std/term.my`, `glob.my`, `args.my`, `bench.my`, `text.my`, `platform_wasm.my`, and the runtime's exit hook for D187 (coordinate with [[MYLA-419]] in `rt.my`).

- [ ] M22: `LineEdit.render` linear in the line's length (2,000 pasted characters: 10 s) ([[MYLA-350]])
- [ ] D187: raw mode is restored by a runtime exit hook on every end of the program
- [ ] [[MYLA-326]]'s follow-up: `glob_in` agrees with `walk` + `matches` for a dangling link named literally and a file before `/**`
- [ ] [[MYLA-333]]'s follow-ups: after `--` a command is an argument; a subcommand's error prints its own usage; a spec is validated
- [ ] [[MYLA-403]]'s follow-up: `std.bench` times a closure that returns nothing (after [[MYLA-417]]'s M24)
- [ ] [[MYLA-341]]'s follow-ups: `wrap` and `columns` count the same unit; `ints` returns an error on a number out of range
- [ ] [[MYLA-336]]'s and [[MYLA-339]]'s follow-ups: wasm32's errno table (unknown errnos aren't EIO), its seek edge cases, `lookup("localhost")`
