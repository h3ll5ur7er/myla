---
id: MYLA-758
title: "The agent harness becomes the project examples/agent/, configured from a TOML file"
type: improvement
status: review
priority: medium
labels: [examples, agent]
---

`examples/agent.my` ([[MYLA-757]]) grows past one file with the features of this epic. It becomes a Myla project, `examples/agent/` (`myla.toml`, `src/`), whose modules each hold one concern: the chat API, the transport, the tools, skills, memory, the context, the session loop, the offline stand-in for the server, the command line.

- [x] `examples/agent/myla.toml`, `src/main.my` and one module per concern; `examples/agent.my` moved there (`git mv`)
- [x] `Config`: server, model, API key, context window, reply tokens, turns, read page size, streaming, command policy, compaction threshold, memory and skill directories; defaults, then `$XDG_CONFIG_HOME/myla-agent/config.toml` (or `~/.config/…`) or `--config FILE`, then `MYLA_AGENT_SERVER`, `MYLA_AGENT_MODEL`, `MYLA_AGENT_API_KEY`, then the command line. A workspace can't configure the agent that works in it (it could allow commands)
- [x] The command line with std.args: `agent [-C DIR] [--config FILE] [--server URL] [--model M] [--no-stream] [--yes] [--demo] [TASK]`; without a task the REPL ([[MYLA-764]])
- [x] `--demo` plays the offline conversation, and a `#test` checks it end to end
- [x] `myla test` in `examples/agent/` passes; a burn test runs it
- [x] A wiki page on the harness: its modules, the loop, what each feature does

Measured on 2026-11-17: `myla test` in `examples/agent/` passes 215 cases in 12 files, interpreted and `--native`; `tests/burn/test_agent.py` passes (2 tests, 8 s); `build/agent --demo` natively prints what `myla run --demo` prints. The page is [[Architecture/Agent-harness]].
