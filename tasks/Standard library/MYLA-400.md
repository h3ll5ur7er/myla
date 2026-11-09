---
id: MYLA-400
title: "The Option helpers of std.map's and std.args's tests go once the seed knows == on Option"
type: chore
status: review
priority: low
labels: [stdlib, cleanup]
---
Left by [[MYLA-379]], which gave `Option` and `Result` `==` and removed the wave 3 modules' `match` helpers for it. Two modules keep theirs: the toolchain compiles std.map (implicit) and std.args (the CLI's) with the seed, and the seed of the day doesn't know `==` on an `Option` (`operator '==' is not defined for 'Option<int32>'` in the bootstrap's embed step). Once a seed with MYLA-379 is in:

- [x] std.map's test helpers `holds` and `none` go: `m.get("ann") == Some(31)`, `m.get("cy") == None`
- [x] std.args's test helper `is` goes: `a.get("out") == Some("x")`
- [x] the bootstrap and `test_std_modules` pass

## Evidence

Built on 7b328dd (master after #55, whose seed has MYLA-379's `==` on `Option`).

- `lib/std/map.my`: `holds` and `none` and their comment are gone; `map_get`'s eleven checks read `m.get("ann") == Some(31)`, `gone.get("bob") == None`. `lib/std/args.my`: `is` is gone; its fifteen checks read `a.get("out") == Some("x")`.
- `build/myla test lib/std/map.my --stdlib lib`: 11/11, and 11/11 with `--native`; `lib/std/args.my`: 26/26 and 26/26.
- `scripts/bootstrap.sh`: the byte-identical fixed point (18,857,370 bytes) with the changed std.map and std.args compiled by the seed and embedded, where the seed before #55 stopped with `operator '==' is not defined for 'Option<int32>'`.
- `python3 -m unittest tests.burn.test_std_modules`: OK (3 min 30 s).
