---
id: MYLA-334
title: "std.time and std.log: civil time, durations, logging"
type: feature
status: backlog
priority: medium
labels: [stdlib, time, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #61, #62. UTC only: time zones need tzdata and come later.

- **Owns:** `lib/std/time.my` (additions), `lib/std/log.my`, `docs/Language/Standard-library/Time.md`, `docs/Language/Standard-library/Log.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `Duration` (nanoseconds, arithmetic, printing as `1.5s`, `250ms`)
- [ ] UTC civil time from the clock: `DateTime` with year to nanosecond, weekday, day of the year; from and to Unix time
- [ ] ISO 8601 and RFC 3339 parsing and printing
- [ ] `std.log`: `error`, `warn`, `info`, `debug` to the standard error with a timestamp, the level from `MYLA_LOG`
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
