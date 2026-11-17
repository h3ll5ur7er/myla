---
id: MYLA-757
title: "An example: an agentic AI harness on the Messages API"
type: feature
status: review
priority: medium
labels: [examples, http, json]
---
`examples/agent.my`: Claude works on a directory through three tools (`list_files`, `read_file`, `write_file`, kept inside the directory) in the Messages API's tool-use loop: the request with the tools and the whole conversation, the assistant's content sent back unchanged, every tool result of a turn in one user message, until `end_turn`, a refusal, `max_tokens` or 20 turns. Built only from the standard library: std.json for the wire format, std.http for a plain-HTTP host, curl through std.process for HTTPS (std.http has no TLS; the key goes in a header file, not the command line), std.fs for the tools. Without a task it runs offline against a scripted stand-in for the API on a local port, so the whole loop is an example test.

- [x] The harness, its tools and the loop, with `#test` cases on every function that returns a value
- [x] The offline demo, pinned in `tests/burn/test_examples_run.py`, built natively in `test_examples_compile.py`
- [x] Listed in [[Getting-started]]

## Evidence

- `build/myla test examples/agent.my`: 29/29 passed. `myla run` without a task: the mock conversation lists the notes, reads the two `.txt` files in one turn, writes `summary.md` from what it read, ends; the native build prints the same.
- The HTTPS path against the real API with a dummy key: `failed: authentication_error: invalid x-api-key` (curl's TLS, the headers and the error reading work). No key was available here for a billed run.
- `python3 -m unittest tests.burn.test_examples_run tests.burn.test_examples_compile tests.burn.test_examples_tests`: 85 tests OK.
- A model served locally that speaks the Messages API: `ANTHROPIC_BASE_URL=http://…` goes through std.http, `AGENT_MODEL` names the model, no key needed, and neither the `fallbacks` field nor its beta header is sent (only to `https://api.anthropic.com`). With nothing listening: `failed: connection failed: ConnectionRefused`, exit 1.
- Not covered: std.http has no TLS (roadmap #40), so HTTPS needs curl on the PATH; no streaming (a reply arrives whole).
