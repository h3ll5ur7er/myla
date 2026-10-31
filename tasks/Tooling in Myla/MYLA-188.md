---
id: MYLA-188
title: "Language server: bare completion dumps the workspace, no cancellation, no pathological-input tests"
type: improvement
status: backlog
priority: low
labels: [lsp]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Beyond the crash on deep nesting ([[MYLA-182]]):

- a completion request at a statement start returns every declaration of the workspace (1,554 items in 855 ms with the repository open; keywords first), where completion by type (`p.`) returns two items in 0 ms;
- the server is single-threaded by design (D67), so a slow check (1.5 s for a 20,000-line file) blocks every request meanwhile; the protocol's `$/cancelRequest` is ignored;
- `tests/burn/test_lsp.py` covers no pathological input (deep nesting, a 10 MB file, thousands of open documents) and asserts no latency.

- [ ] Bare completion scoped to the document and its imports, or paginated (`isIncomplete`)
- [ ] Requests answered between the phases of a long check, or cancelled
- [ ] Size and depth tests with time bounds
