---
id: MYLA-400
title: "The Option helpers of std.map's and std.args's tests go once the seed knows == on Option"
type: chore
status: backlog
priority: low
labels: [stdlib, cleanup]
---
Left by [[MYLA-379]], which gave `Option` and `Result` `==` and removed the wave 3 modules' `match` helpers for it. Two modules keep theirs: the toolchain compiles std.map (implicit) and std.args (the CLI's) with the seed, and the seed of the day doesn't know `==` on an `Option` (`operator '==' is not defined for 'Option<int32>'` in the bootstrap's embed step). Once a seed with MYLA-379 is in:

- [ ] std.map's test helpers `holds` and `none` go: `m.get("ann") == Some(31)`, `m.get("cy") == None`
- [ ] std.args's test helper `is` goes: `a.get("out") == Some("x")`
- [ ] the bootstrap and `test_std_modules` pass
