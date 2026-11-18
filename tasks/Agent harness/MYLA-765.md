---
id: MYLA-765
title: "Agent harness: streaming replies"
type: feature
status: review
priority: medium
labels: [examples, agent]
---

std.http gives a response when it is complete, so streaming (`"stream": true`, server-sent events) needs its own small client over std.net: the request, the status and headers, the body as it comes (chunked or not), its `data:` lines.

- [x] The events folded into a reply: text deltas, tool calls by index (their arguments in pieces), the finish reason, `usage` (`stream_options.include_usage`)
- [x] The text printed as it arrives, without the `<think>` part
- [x] Chunked transfer decoding, incremental
- [x] The offline stand-in answers streamed requests with events, so the demo runs streaming
- [x] `--no-stream` and `stream = false` use the plain request

The stand-in sends its replies as events (the text, and each tool call's arguments, in pieces), so the demo and its test run streaming. Against vLLM the text appears as it comes, and white space at its end waits for what follows.
