---
id: MYLA-435
title: "A failing expect points at its caller"
type: improvement
status: backlog
priority: low
labels: [std, diagnostics]
---
[[MYLA-324]]'s follow-up from [[Project/Review-2026-11-09]]: `opt.expect("…")` failing reports a position inside `lib/std/option.my`, not the call.

- [ ] A way for a library function to report its caller's position (as Rust's `#[track_caller]`), on every runner
- [ ] `expect`, `unwrap` and the index helpers use it
