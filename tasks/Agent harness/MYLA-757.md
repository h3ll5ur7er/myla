---
id: MYLA-757
title: "examples/agent.my stays inside the model's context window"
type: bug
status: review
priority: medium
labels: [examples, agent]
---

`examples/agent.my` sends the whole conversation back on every turn, so every file it reads stays in the prompt. Reviewing this repository against a 32,768-token model failed after 13 tool calls (`README.md` … `selfhost/lexer.my`, about 93 KB): "your prompt contains at least 28673 input tokens" plus the 4,096 reserved for the reply.

Done means a long run never sends a request larger than the window, and the model can still reach every line of a large file.

- [x] `read_file` gives a page of a file at most `MAX_READ_BYTES` long, with an optional `start` line, and says where the next page starts
- [x] Before each request, tool results the model has already answered are replaced by a short note, oldest first, until the request fits `CONTEXT_TOKENS - MAX_TOKENS` (estimated at 3 bytes a token, measured: the failed request was about 3.3)
- [x] The history keeps a reply's visible text, not the `<think>` reasoning before it
- [x] `#test` cases for each, the offline demo still plays its conversation
- [x] A run against the real server reviews files past the point the first run failed

The second run against the server (Qwen3.6-35B, 2026-11-17) read `README.md` and 15 more files or pages, among them `selfhost/driver.my` in three pages and `lexer.my`, `parser.my`, `checker.my` and `codegen.my`. It dropped 12 answered results along the way, never went over the window, and stopped at `MAX_TURNS` (20). The first run had failed at turn 13.

[[MYLA-761]] replaced dropping as the way a long conversation stays in the window, as the prefix cache needs ([[MYLA-762]]); `fit` is its fallback in `examples/agent/src/context.my`.
