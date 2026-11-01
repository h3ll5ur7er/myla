---
id: MYLA-178
title: "CLI tracebacks: a directory argument, a broken pipe, a missing output directory, a BOM"
type: bug
status: review
priority: low
labels: [cli]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Four ways to get a Python traceback or a misleading message out of `python3 myla.py`:

- `run examples` (a directory) → raw `IsADirectoryError` (`cli.py` catches only `FileNotFoundError`)
- `tokenize file | head` → `BrokenPipeError` traceback
- `build f.my -o missing/dir/out` → `No such file or directory: '.../out.s'`, naming the intermediate file instead of the directory
- a UTF-8 byte-order mark at the start of a file → `lex error: unexpected character` (both lexers should skip it)

- [x] `OSError` and `BrokenPipeError` handled in `main`; the output directory named in the build error
- [x] The BOM skipped by both lexers (a lexer-gate snippet)
- [x] `build/myla --help` prints the usage and exits 0 instead of `unknown command '--help'`

## Evidence

- `python3 myla.py run examples` → `error: [Errno 21] Is a directory: 'examples'`, exit 1; `tokenize selfhost/codegen.my | head -1` exits 1 without a traceback; `build f.my -o missing/dir/out` → `build error: the output directory '…/missing/dir' doesn't exist`.
- Both lexers skip a leading BOM without counting a column, and both renderers leave it out of the quoted line (lexer gate `test_a_byte_order_mark_is_skipped`, which also checks that a BOM elsewhere is an error in both).
- `build/myla --help` (and `-h`, `help`) prints the usage on stdout and exits 0 (`test_help`).
- Unit 622, integration 2, burn 826 (5 skipped) and the extension's 54 tests pass on commit 12f6e94; the bootstrap reaches its byte-identical fixed point (6,153,392 bytes).
