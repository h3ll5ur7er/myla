# std.log

Messages to the standard error with a time and a level ([[MYLA-334]]). Each is one line:

```text
2026-11-07T17:00:00.123Z INFO message
```

the time in UTC with milliseconds (`std.time.format_rfc3339_millis`, [[Language/Standard-library/Time]]), the level and the message.

```myla
import std.log as log
from std.log import Level
import std.time as time

fun main() {
    log.info("starting")  // to the standard error, if MYLA_LOG lets it through
    let at = match time.parse_rfc3339("2026-11-07T17:00:00.123Z") {
        Ok(t) => t
        Err(e) => { panic(f"{e}") }
    }
    print(log.line(at, Level.Warn, "disk almost full"))
    match log.threshold(Some("Info")) {
        Some(max) => print(max.name())
        None => print("off")
    }
    let quiet = log.logger_at(Some(Level.Error))
    print(quiet.enabled(Level.Warn))
}
// output:
// 2026-11-07T17:00:00.123Z WARN disk almost full
// INFO
// false
```

| Function | Writes |
| --- | --- |
| `error(message: str)` | An error: something failed |
| `warn(message: str)` | A warning: something may be wrong |
| `info(message: str)` | Information on what the program does |
| `debug(message: str)` | Detail for finding a fault |
| `log(level: Level, message: str)` | A message of the level |

`Level` is the enum `Error`, `Warn`, `Info`, `Debug`, the most important first, with `name()` (`ERROR`, `WARN`, `INFO`, `DEBUG`), `rank()` (1 to 4) and `==`.

## Which levels get through

The environment variable `MYLA_LOG` says which: `error`, `warn`, `info`, `debug` (everything) or `off` (nothing). Unset, or set to a value it doesn't know, it is `warn`. Spaces around it and its case don't matter.

| Function | Result |
| --- | --- |
| `threshold(setting: Option<str>) -> Option<Level>` | The most verbose level a setting lets through, `None` for `off` |
| `current() -> Option<Level>` | `threshold(std.process.env("MYLA_LOG"))` |
| `enabled(level: Level) -> bool` | Whether a message of the level gets through now: to skip building one that would be dropped |
| `line(at: DateTime, level: Level, message: str) -> str` | The line that would be written, without the newline |

Myla has no global variables (D28), so each call reads `MYLA_LOG` again. A `Logger` reads it once and keeps what it read:

| Function | Result |
| --- | --- |
| `logger() -> Logger` | A logger with `MYLA_LOG`'s threshold as it is now |
| `logger_at(max: Option<Level>) -> Logger` | A logger with a threshold of the program's own; `None` writes nothing |

It has the methods `error`, `warn`, `info`, `debug`, `log` and `enabled`, as the functions.

Measured natively on x86-64, best of three runs, with 168 environment variables:

| Call | Time |
| --- | --- |
| `log.debug(m)`, dropped | 0.23 µs: reading `MYLA_LOG` |
| `logger.debug(m)`, dropped | 6 ns |
| `log.warn(m)`, written to `/dev/null` | 1.45 µs |
| `logger.warn(m)`, written to `/dev/null` | 1.22 µs: the wall clock (0.18 µs), the text and the write |

So per call is fine for most programs; a loop that logs a lot takes a `Logger`.

A line is one write to the descriptor, so the lines of tasks that run at once don't mix. The functions don't fail: a closed standard error ends the program quietly, as `eprint` does (D146).
