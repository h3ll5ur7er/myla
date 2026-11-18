---
id: MYLA-762
title: "Agent harness: a prompt the server's prefix cache can reuse"
type: feature
status: review
priority: medium
labels: [examples, agent]
---

OpenAI-style servers cache the prompt by its prefix (vLLM's automatic prefix caching, llama.cpp's `cache_prompt`). The harness keeps the prefix stable so that each request reuses the last one's: the system prompt and the tools are built once per session (no time, nothing that changes), the conversation is only appended to, and the only rewrite is a compaction ([[MYLA-761]]).

- [x] The system prompt and tools fixed for a session; memory and skill changes noted in tool results, not in the prompt
- [x] The conversation append-only between compactions
- [x] `usage` read, with `prompt_tokens_details.cached_tokens`; the session's totals and the cache's share in `/stats` and at the end of a run
- [x] `cache_prompt: true` for llama.cpp's server (others ignore it)

The server at hand (vLLM) reports no `cached_tokens` without `--enable-prompt-tokens-details`, and the statistics say so. The stand-in counts as a prefix cache would: 76 % of the demo's prompt tokens.
