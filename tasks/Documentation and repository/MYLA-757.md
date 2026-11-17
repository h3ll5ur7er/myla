---
id: MYLA-757
title: "An example: an agentic AI harness"
type: feature
status: review
priority: medium
labels: [examples, http, json]
---
`examples/agent.my`: a model works on a directory through three tools (`list_files`, `read_file`, `write_file`, kept inside the directory) in a tool-call loop: the request with the tools and the whole conversation, the model's message sent back, a `tool` message for each call's result, until it answers without a call, is cut off, or 20 turns pass. It talks to a model served on the network with the OpenAI-style chat completions API (the owner's vLLM serving Qwen3.6), configured only by constants at its top (server, model, optional API key, token limit), over std.http and std.json; no curl, no environment variables, no external service. Qwen3's `<think>` reasoning is left out of what it prints. Without a task it runs offline against a scripted stand-in for the server on a local port, so the whole loop is an example test.

- [x] The harness, its tools and the loop, with `#test` cases on every function that returns a value
- [x] The offline demo, pinned in `tests/burn/test_examples_run.py`, built natively in `test_examples_compile.py`
- [x] Listed in [[Getting-started]]

## Evidence

- `build/myla test examples/agent.my`: 32/32 passed. `myla run` without a task: the stand-in lists the notes, reads the two `.txt` files in one turn, writes `summary.md` from what it read, ends; its first reply's `<think>` block isn't printed. The native build prints the same.
- From this container `jarvis` doesn't resolve: `failed: http://jarvis:9293: connection failed: NotFound`, exit 1. Not yet run against the real server.
- First version (Anthropic's Messages API, HTTPS through curl) replaced at the owner's request: a local model, plain HTTP, configured in code. HTTPS waits for TLS (roadmap #40).
- Not covered: no streaming (a reply arrives whole); std.net's resolver doesn't apply resolv.conf's search domains, so a short host name needs /etc/hosts or a DNS server that answers it.
