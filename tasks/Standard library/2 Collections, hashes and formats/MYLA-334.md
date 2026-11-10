---
id: MYLA-334
title: "std.time and std.log: civil time, durations, logging"
type: feature
status: done
priority: medium
labels: [stdlib, time, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #61, #62. UTC only: time zones need tzdata and come later.

- **Owns:** `lib/std/time.my` (additions), `lib/std/log.my`, `docs/Language/Standard-library/Time.md`, `docs/Language/Standard-library/Log.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `Duration` (nanoseconds, arithmetic, printing as `1.5s`, `250ms`)
- [x] UTC civil time from the clock: `DateTime` with year to nanosecond, weekday, day of the year; from and to Unix time
- [x] ISO 8601 and RFC 3339 parsing and printing
- [x] `std.log`: `error`, `warn`, `info`, `debug` to the standard error with a timestamp, the level from `MYLA_LOG`
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- **The API** ([[lib/std/time.my]], [[Language/Standard-library/Time]]): `now_ns` and `now_ms` as they were; `Duration { ns: int64 }` from `nanos`, `micros`, `millis`, `seconds`, `minutes`, `hours`, with `+`, `-`, `==`, the comparisons, `as_nanos`, `as_micros`, `as_millis`, `as_secs`, `as_secs_f64`, `abs`, `mul_int`, `div_int`, and Go's printing through `Format`; `Instant` from `now()`, with `elapsed`, `since`, `add` and the comparisons; `DateTime` in UTC (`year` … `nanosecond`) from `now_utc`, `datetime`, `date`, `from_unix(secs, nanos)`, `from_unix_ns`, with `to_unix`, `to_unix_ns`, `weekday` (the enum `Weekday`), `day_of_year`, `add(Duration)`, `diff`, the comparisons and `Format`; `is_leap_year`, `days_in_month`; `parse_rfc3339`, `parse_iso8601`, `format_rfc3339`, `format_rfc3339_millis`, `format_iso8601_basic`, `format_date`; `TimeError` (`Syntax(at)`, `Field(name)`, `OutOfRange`). [[lib/std/log.my]] ([[Language/Standard-library/Log]]): `error`, `warn`, `info`, `debug`, `log`, `enabled`, `current`, `threshold`, `line`, the enum `Level`, and a `Logger` (`logger()`, `logger_at(max)`) that reads `MYLA_LOG` once.
- **The wall clock** is a new platform primitive, `__wall_ns()`, the way [[MYLA-336]]'s are: `std.rt.wall_ns` over `std.platform`'s `wall_ns` (`clock_gettime(CLOCK_REALTIME)` on x86-64 and aarch64, `clock_time_get` with clock 0 on WASI), the host's own in the interpreter, and one name in the checker's `is_platform_primitive`. No seed staging (D156): the seed compiles only the compiler, which calls no new primitive; the bootstrap from the unchanged seed reaches the fixed point (12320795 bytes).
- **Tests first:** `std.log`'s cases over stubs gave `1/9 passed`. A broken `days_from_civil` and `civil_from_days` (an epoch off by one day, a month off at March) failed 25 of std.time's cases. Now `build/myla test lib/std/time.my --stdlib lib`: `149/149 passed` interpreted, with `--native`, `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (Node); `lib/std/log.my`: `26/26` on the same four. After `scripts/bootstrap.sh`, `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks`: `Ran 6 tests … OK`; `tests.burn.test_platform_primitives tests.burn.test_allow` OK as well.
- **Cross-checks:** a test function round-trips every day from 1970 to 2100 through `from_unix` and `to_unix` (and checks each day follows the one before, the weekday and the day of the year; every 7th day through RFC 3339's text too), another every 97th day of the years 1 to 9999 through both of Hinnant's functions. A scratch script compared 5007 instants from year 1 to 9999 with Python's `datetime` (RFC 3339 text, ISO weekday, day of the year, Unix seconds, and the same instant written with an offset parsed back): the same output interpreted, natively, under qemu-aarch64 and on wasm32 under Node. 2014 durations print exactly as Go's `time.Duration.String`, the most negative one included.
- **Measurements** (natively on x86-64, best of three): `log.debug(m)` dropped 0.23 µs (reading `MYLA_LOG`, 168 variables in the environment), through a `Logger` 6 ns; `log.warn(m)` written to `/dev/null` 1.45 µs, through a `Logger` 1.22 µs; `now_utc()` 0.18 µs. Per call is fine; the `Logger` is there for loops. Checking a program that imports `std.test` (which imports `std.time`): 38 ms before, 45 ms after; with `std.fmt`'s `pad` imported it was 64 ms, so std.time has a small `pad` of its own.
- **Found:** MYLA-360 holds for `std.str` too: a module of `lib/std` that imports `.str` runs std.str's 106 method cases as its own, and its `--native` harness doesn't parse. `std.log` has its own `normalized` instead of `trim` and `to_lower`.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-425]]: `Duration.abs()` of the minimum and "arithmetic wraps" are runtime errors wherever overflow is checked.
