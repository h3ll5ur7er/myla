---
id: MYLA-17
title: "Native runtime robustness: partial writes and malformed UTF-8"
type: bug
status: backlog
priority: low
labels: [native-backend, runtime]
---
Small gaps in the hand-written runtime:

- `__print_str`, `__write` and `__panic` issue one `write` syscall and ignore short writes and `EINTR` ([[src/myla/compiler/codegen_x86.py#L4426-L4437]]). Blocking pipes and files rarely return short, but a signal or a non-blocking stdout can truncate output.
- `__str_chars` assumes well-formed UTF-8 and reads up to three bytes past the end of a truncated sequence ([[src/myla/compiler/codegen_x86.py#L4326-L4424]]). Files read with `std.fs` can hold anything.
- `__trap` exits 1 silently: an out-of-bounds index, a missing map key or a division by zero gives no message natively, while the interpreter names the error.

## Done when

- [ ] Write loops until all bytes are written, retrying on `EINTR`
- [ ] `__str_chars` bounds-checks every continuation byte (replace invalid sequences with U+FFFD, the same in the interpreter)
- [ ] `__trap` takes a message (`index out of bounds`, `map key not found`, `division by zero`) and writes it to stderr
