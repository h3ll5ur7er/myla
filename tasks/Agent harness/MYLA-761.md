---
id: MYLA-761
title: "Agent harness: context compaction by summary"
type: feature
status: review
priority: medium
labels: [examples, agent]
---

[[MYLA-757]] keeps a run inside the window by dropping answered tool results, which loses what the model read and changes the prompt's prefix at every drop ([[MYLA-762]]). Compaction instead: when the conversation passes a threshold of the window (`compact_at`, 75 % by default), the harness asks the model for a summary of the work so far and starts the conversation again from the system prompt, the first request and the summary.

- [x] The size from the server's `usage` (prompt and completion tokens of the last reply) plus an estimate of what was added since
- [x] The summary request: the conversation (fitted by dropping if it must be) and an instruction for what a summary keeps (the task, decisions, files and findings, what remains)
- [x] The conversation after it: system, first request, summary, and the newest turn as it is; dropping stays the fallback when the summary fails
- [x] `/compact` in the REPL

With `context_tokens = 12000` and `compact_at = 60` (2026-11-17), reading `README.md`, `AGENTS.md` and `docs/Home.md` compacted twice and stayed in the window. Summing up the newest turn too had made the model read `README.md` again: 9 requests and 35,190 prompt tokens, against 7 and 27,063 with the turn kept.
