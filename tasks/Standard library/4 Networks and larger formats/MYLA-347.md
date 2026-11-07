---
id: MYLA-347
title: "std.http: an HTTP/1.1 client and server"
type: feature
status: backlog
priority: low
labels: [stdlib, net, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #48. Plain HTTP; HTTPS waits for TLS (roadmap #40).

- **Owns:** `lib/std/http.my`, `docs/Language/Standard-library/Http.md`
- **Needs:** [[MYLA-346]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] Requests and responses, headers, chunked bodies, keep-alive
- [ ] A client (`get`, `post`, a request builder) and a server with a handler function, on the reactor
- [ ] Gzip bodies through [[MYLA-344]]
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
