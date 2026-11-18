---
id: MYLA-764
title: "Agent harness: an interactive REPL"
type: feature
status: review
priority: medium
labels: [examples, agent]
---

Without a task the harness reads requests one after the other (std.term's line editor on a terminal, plain lines otherwise) and keeps one conversation.

- [x] The loop: each line a request, the model's turns until it answers, then the next line; Ctrl-D or `/exit` ends it
- [x] Commands: `/help`, `/exit`, `/clear` (a new conversation), `/compact`, `/stats`, `/skills`, `/memory`
- [x] A failed request is reported and the session goes on

Checked on 2026-11-17 with piped lines against the server: `/help`, a request, `/stats`, `/memory`, `/skills`, an unknown command, `/exit`.
