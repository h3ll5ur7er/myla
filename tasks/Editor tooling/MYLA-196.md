---
id: MYLA-196
title: "Snippets for actor, async fun, async let and #main; stdout latency in the debug adapter"
type: chore
status: backlog
priority: low
labels: [vscode]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]).

- `vscode-extension/myla/snippets/myla.code-snippets` has 17 snippets and none for `actor`, `async fun`, `async let` or `#main async fun main()`
- the debug adapter reads the program's output from files polled every 100 ms (D78), so output appears late, and the program's stdin is a file (`/dev/null` by default), so an interactive program can't be debugged; a pseudo-terminal would need a native module. Worth a line in [[Development/Debugging]] if it stays

- [ ] The four snippets, tied to the lexer's keyword list by `tests/unit/test_vscode_extension.py`
- [ ] The two limits documented
