---
id: MYLA-49
title: Language server lifecycle bugs
type: bug
status: done
priority: low
labels: [lsp]
---
- [ ] `did_close` doesn't cancel a pending debounce timer; when it fires, `publish_for` reads the file from disk with empty `source_lines`, so stale diagnostics at (0,0) can reappear for a closed file ([[src/myla/lsp/server.py]])
- [ ] Diagnostics are published from `threading.Timer` threads while handlers run on the asyncio loop; pygls's writer isn't documented as thread-safe. Debounce with `asyncio` instead
- [ ] Only the current buffer is passed to the loader as an override; other unsaved buffers are read from disk, and files that import a changed module aren't re-checked
- [ ] Override keys are `to_fs_path(uri)` while indexed files are `realpath`, so unsaved edits are missed under symlinked roots ([[src/myla/lsp/workspace.py]])
- [ ] Errors from imported modules land on the open document: [[MYLA-10]]

## Superseded

Closed without a fix: superseded by [[MYLA-80]] (the Python language server will be replaced by one written in Myla, which takes these findings as requirements, see [[Project/Roadmap]]).
