---
id: MYLA-17
title: "Native runtime robustness: partial writes and malformed UTF-8"
type: bug
status: done
priority: low
labels: [native-backend, runtime]
---
Small gaps in the hand-written runtime:

- `__print_str`, `__write` and `__panic` issue one `write` syscall and ignore short writes and `EINTR` ([[src/myla/compiler/codegen_x86.py#L4426-L4437]]). Blocking pipes and files rarely return short, but a signal or a non-blocking stdout can truncate output.
- `__str_chars` assumes well-formed UTF-8 and reads up to three bytes past the end of a truncated sequence ([[src/myla/compiler/codegen_x86.py#L4326-L4424]]). Files read with `std.fs` can hold anything.
- `__trap` exits 1 silently: an out-of-bounds index, a missing map key or a division by zero gives no message natively, while the interpreter names the error.

## Done when

- [x] Write loops until all bytes are written, retrying on `EINTR`
- [x] `__str_chars` bounds-checks every continuation byte (replace invalid sequences with U+FFFD, the same in the interpreter): done with [[MYLA-12]]
- [x] `__trap` takes a message (`index out of bounds`, `map key not found`, `division by zero`) and writes it to stderr

## How

In both runtimes ([[src/myla/compiler/codegen_x86.py]], [[selfhost/codegen.my]]):

- `__write_all` writes a buffer with as many `write` calls as it takes: a short write continues with the rest, `EINTR` and `EAGAIN` (a full non-blocking pipe) retry, another error gives up. `__print_str`, `__print_int`/`__print_uint`, `__print_bool`, `__print_nl`, `__write`, `__panic` (and the self-hosted `__print_char`) go through it. `__write_file` already looped over short writes.
- Each kind of runtime error jumps to its own entry (`__trap_index`, `__trap_key`, `__trap_pop`, `__trap_div`, `__trap_mod`, `__trap_match`, `__trap_oom`), which prints `runtime error: <message>` through `__panic`: the interpreter's message without the values (the native code doesn't keep them).

## Evidence

[[tests/burn/test_native_runtime.py]], for the Python backend and the self-hosted compiler:

- Seven runtime errors (list and string index, map key, element assignment, `pop` on an empty list, division and modulo by zero) print `runtime error: <message>` and exit 1. Before: nothing on stderr.
- A program writing 2,020,000 bytes to a non-blocking pipe whose reader starts 0.3 s late: before, only 64,696 bytes arrived (one pipe buffer; the rest was silently dropped); after, all of them.

