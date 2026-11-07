---
id: MYLA-350
title: std.term and std.signal
type: feature
status: backlog
priority: low
labels: [stdlib, terminal, primitives, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #63, #64. The platform track's third task: `ioctl` for the terminal and signal handling need primitives.

- **Owns:** `lib/std/term.my`, `lib/std/signal.my`, `lib/std/platform*.my`, `selfhost/` (primitives)
- **Needs:** [[MYLA-336]]

- [ ] ANSI colours and styles; `is_tty`; the terminal's size; raw mode
- [ ] SIGINT and SIGTERM as an async event a program awaits
- [ ] The REPL's line editing moved onto `std.term` as the proof
