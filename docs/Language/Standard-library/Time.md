# std.time

The clocks, durations and civil time in UTC (D124, [[MYLA-230]], [[MYLA-334]]). There are two clocks:

- the **monotonic** clock, `now_ns`, `now_ms` and `now()`: it never goes back and doesn't follow changes to the date, so the difference of two readings is the time that passed. Its zero is some fixed point in the past, not a date. Measure with it.
- the **wall** clock, `now_utc()`: the date and time in UTC, which follows the system's date and so can go back. Tell the time with it.

```myla
import std.time as time

fun main() {
    let d = time.hours(2) + time.minutes(3) + time.seconds(4)
    print(f"{d} {time.millis(1500)} {time.micros(250)} {d.as_secs_f64()}")
    print(time.millis(250) < time.seconds(1))

    let t = match time.parse_rfc3339("2026-11-07T18:00:00.123+01:00") {
        Ok(t) => t
        Err(e) => { panic(f"{e}") }
    }
    print(f"{t} {t.weekday()} day {t.day_of_year()} unix {t.to_unix()}")
    let later = match t.add(time.hours(30)) {
        Ok(l) => l
        Err(e) => { panic(f"{e}") }
    }
    print(f"{time.format_iso8601_basic(later)} {later.diff(t)}")
    match time.parse_rfc3339("2016-12-31T23:59:60Z") {
        Ok(_) => print("parsed")
        Err(e) => print(f"{e}")
    }

    let start = time.now()
    let now = time.now_utc()
    print(now.year >= 2026 && start.elapsed() >= time.nanos(0))
}
// output:
// 2h3m4s 1.5s 250µs 7384
// true
// 2026-11-07T17:00:00.123Z Saturday day 311 unix 1794070800
// 20261108T230000.123Z 30h0m0s
// second out of range
// true
```

## The monotonic clock

| Function | Result |
| --- | --- |
| `now_ns() -> int64` | The clock in nanoseconds |
| `now_ms() -> int64` | The clock in milliseconds |
| `now() -> Instant` | The clock as an `Instant` |

The interpreter reads the same clock; with `MYLA_TIME=virtual` it reads one that moves only when no task is ready, to the next sleeper's deadline, so tests of timing logic take no time and order exactly. The wall clock stays the real one there.

An `Instant` is a reading. It has `==` and the comparisons.

| Method | Result |
| --- | --- |
| `elapsed() -> Duration` | The time since the reading |
| `since(earlier: Instant) -> Duration` | The time from `earlier` to this reading; negative if `earlier` is later |
| `add(d: Duration) -> Instant` | The reading `d` later |

## Duration

A `Duration` is a span of time in nanoseconds, an `int64` in its field `ns`: about 292 years either way, positive or negative. Arithmetic wraps as `int64` does.

| Function | Result |
| --- | --- |
| `nanos(n: int64)`, `micros(n)`, `millis(n)`, `seconds(n)`, `minutes(n)`, `hours(n)` | `n` of the unit |

`+`, `-`, `==` and the comparisons work on two durations.

| Method | Result |
| --- | --- |
| `as_nanos()`, `as_micros()`, `as_millis()`, `as_secs() -> int64` | The whole units, rounded toward zero |
| `as_secs_f64() -> float64` | The seconds as a float |
| `abs() -> Duration` | Without the sign |
| `mul_int(k: int64)`, `div_int(k: int64) -> Duration` | `k` times; divided by `k`, rounded toward zero |

A duration prints as Go prints one: `0s`; below a second one unit, `ns`, `µs` or `ms`, with a fraction (`1.1µs`, `250ms`); from a second on hours, minutes and seconds with the leading zero ones left out (`1.5s`, `1m0s`, `2h3m4s`). A fraction has no trailing zeros. A spec gives the text a width, `{d:>8}`. 2000 random durations and the edge cases print as Go's `time.Duration.String` prints them.

## DateTime

A `DateTime` is a civil time in UTC, with the fields `year` (1 to 9999), `month` (1 to 12), `day`, `hour`, `minute`, `second` and `nanosecond`, all `int`. The calendar is the proleptic Gregorian one, so the years before 1582 follow today's rules too. A `DateTime` made by the functions below is always a valid one. It has `==` and the comparisons, and prints as `format_rfc3339` writes it.

| Function | Result |
| --- | --- |
| `now_utc() -> DateTime` | The wall clock now |
| `datetime(year, month, day, hour, minute, second, nanosecond) -> Result<DateTime, TimeError>` | The time from its fields, if they make one |
| `date(year, month, day) -> Result<DateTime, TimeError>` | Midnight of the date |
| `from_unix(secs: int64, nanos: int64) -> Result<DateTime, TimeError>` | The time `secs` seconds and `nanos` nanoseconds after 1970-01-01T00:00:00Z; either may be negative |
| `from_unix_ns(ns: int64) -> DateTime` | The time `ns` nanoseconds after it: every `int64` is one, from 1677 to 2262 |
| `is_leap_year(year: int) -> bool` | Whether the year has a February 29th |
| `days_in_month(year: int, month: int) -> int` | 28 to 31; 0 for a month that isn't one |

| Method | Result |
| --- | --- |
| `to_unix() -> int64` | The whole seconds since 1970-01-01T00:00:00Z, negative before |
| `to_unix_ns() -> Result<int64, TimeError>` | The nanoseconds since then, if they fit an `int64` |
| `weekday() -> Weekday` | The day of the week |
| `day_of_year() -> int` | 1 to 366 |
| `add(d: Duration) -> Result<DateTime, TimeError>` | The time `d` later, earlier for a negative `d` |
| `diff(other: DateTime) -> Duration` | The time from `other` to this one; past about 292 years either way the longest `Duration` of its sign, as Go's `Time.Sub` gives |

`Weekday` is the enum `Monday` … `Sunday`, with `number()` (ISO 8601's, Monday 1 to Sunday 7) and `name()` (`Monday`); it prints its name.

**No leap seconds.** Every day has 86400 seconds, as in Unix time, so a time never has a second of 60, and `23:59:60` doesn't parse: `Field("second")`.

**No time zones yet.** They need the tz database, and come later. An offset in a text (`+01:00`) is applied when it is read, and the result is in UTC; there is no way to write one.

### How it works

The days are counted with Howard Hinnant's [`days_from_civil` and `civil_from_days`](http://howardhinnant.github.io/date_algorithms.html). They shift the year to start on March 1st, so February's leap day is the last day of the year, and split time into eras of 400 years, 146097 days each. Within an era the year and the day of the year come out of integer divisions, without a loop and without tables. The cases check every day from 1970 to 2100 through `from_unix` and `to_unix`, every 97th day of the whole range both ways, and 5000 random instants from year 1 to 9999 agree with Python's `datetime`, in the interpreter, natively, on aarch64 and on wasm32.

The wall clock is the primitive `__wall_ns`: `clock_gettime(CLOCK_REALTIME)` on Linux and WASI's `clock_time_get` with the realtime clock ([[Language/Targets]]). Natively a reading costs about 0.2 µs, as it is a system call.

## Text

| Function | Result |
| --- | --- |
| `parse_rfc3339(s) -> Result<DateTime, TimeError>` | RFC 3339's form, `2026-11-07T17:00:00Z`, `…00.123+01:00` |
| `parse_iso8601(s) -> Result<DateTime, TimeError>` | ISO 8601's extended or basic form, see below |
| `format_rfc3339(t) -> str` | `2026-11-07T17:00:00Z`, with a fraction when the nanoseconds aren't 0, without trailing zeros: `…00.5Z` (Go's `RFC3339Nano`) |
| `format_rfc3339_millis(t) -> str` | `2026-11-07T17:00:00.123Z`: always three digits, rounded down, as `std.log` writes it |
| `format_iso8601_basic(t) -> str` | `20261107T170000Z`, the fraction as in `format_rfc3339` |
| `format_date(t) -> str` | `2026-11-07` |

`parse_rfc3339` takes four digits of year, `-`, month, `-`, day, `T` (or `t` or a space), hour, `:`, minute, `:`, second, a fraction after `.` if there is one, and `Z` (or `z`) or an offset `+hh:mm` or `-hh:mm`. Digits of the fraction past the ninth are read and dropped. `-00:00` is UTC.

`parse_iso8601` takes those and also a date alone (midnight), a time without seconds (`T17:00`), a fraction after `,`, an offset of hours alone (`+01`) or without the colon (`+0100`), and no zone at all, which is taken as UTC, as there are no local times yet. Its basic form has no separators, `20261107T170000Z`; the time takes the date's form, so `2026-11-07T1700` is an error.

## Errors

`TimeError` is an enum with `==`; `message()` gives it in words, and it prints them.

| Variant | Meaning |
| --- | --- |
| `Syntax(at: int)` | The text doesn't have the form at this byte offset |
| `Field(name: str)` | A field outside its range: `"year"`, `"month"`, `"day"`, `"hour"`, `"minute"`, `"second"`, `"nanosecond"` or `"offset"` |
| `OutOfRange` | The time is outside the years 1 to 9999 (an offset can push a valid text out) |
