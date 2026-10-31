---
id: MYLA-178
title: "CLI tracebacks: a directory argument, a broken pipe, a missing output directory, a BOM"
type: bug
status: todo
priority: low
labels: [cli]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Four ways to get a Python traceback or a misleading message out of `python3 myla.py`:

- `run examples` (a directory) → raw `IsADirectoryError` (`cli.py` catches only `FileNotFoundError`)
- `tokenize file | head` → `BrokenPipeError` traceback
- `build f.my -o missing/dir/out` → `No such file or directory: '.../out.s'`, naming the intermediate file instead of the directory
- a UTF-8 byte-order mark at the start of a file → `lex error: unexpected character` (both lexers should skip it)

- [ ] `OSError` and `BrokenPipeError` handled in `main`; the output directory named in the build error
- [ ] The BOM skipped by both lexers (a lexer-gate snippet)
- [ ] `build/myla --help` prints the usage and exits 0 instead of `unknown command '--help'`
