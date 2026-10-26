---
id: MYLA-82
title: REPL written in Myla
type: feature
status: backlog
priority: low
labels: [repl, selfhost]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]). Supersedes [[MYLA-19]] (the Python `myla repl` stub). Built on the self-hosted interpreter ([[selfhost/interp.my]]; its performance is [[MYLA-74]]) and stdin ([[MYLA-78]]).

- [ ] Line-by-line input; an open brace continues the input
- [ ] Declarations accumulate; an expression prints its value
- [ ] Errors are reported without ending the session
