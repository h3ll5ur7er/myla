---
id: MYLA-422
title: "P8 HTTP and URL: chunk sizes, timeouts, replay, resolution"
type: bug
status: todo
priority: high
labels: [std, http, url, security, round-5]
---
Work package P8 of [[Project/Review-2026-11-09]] (wave A2). Files: `lib/std/http.my`, `lib/std/url.my`. Reopens [[MYLA-347]].

- [ ] H7: a chunk size that overflows `body_len + size` is refused, checked and plain (D184)
- [ ] M23: a write timeout, and an idle timeout separate from a connection's life (a client that never reads holds a worker; 64 idle connections stop a default server; `keep_alive_ms` cuts a slow upload)
- [ ] M23: a dropped kept connection doesn't replay a non-idempotent request
- [ ] `url.resolve` with dot segments, used by the redirects ([[MYLA-329]])
- [ ] [[MYLA-329]]'s follow-up: `Url.to_str` keeps a port's leading zeros out (or refuses them)
- [ ] Two `Host` fields, a NUL and a bare CR in a header are refused
