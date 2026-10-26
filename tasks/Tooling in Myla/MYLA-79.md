---
id: MYLA-79
title: JSON in the standard library
type: feature
status: backlog
priority: medium
labels: [stdlib]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]); the language server's protocol is JSON-RPC ([[MYLA-80]]).

- [ ] `std.json`: a `Json` enum (null, bool, number, string, array, object), a parser with positioned errors, and a serializer (string escapes, `\u` and surrogate pairs)
- [ ] Written in Myla, tested with `#test` and against Python's `json` on a corpus
