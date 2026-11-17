---
id: MYLA-795
title: "R7-6 Router and JSON: static_files on Windows (H8), JSON numbers (H9), patterns (M14)"
type: bug
status: todo
priority: high
labels: [http, json, security, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "Router and JSON" (section 5). Files: `lib/std/http.my` (the router: `static_files`, `file_response`, patterns, `json_body`; the server is [[MYLA-794]]'s), `lib/std/json.my`. The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. The owner's decisions it builds as the review recommends: 6. New tasks it files take ids 841–848.

- [ ] **H8** (high, new, Windows target): `GET /assets/..%5ctopsecret.txt` is `200`: `file_response` splits on `/` only; `app.css.`, `app.css%20` and `nul` are served. `repro-r6/runtime-http/router_static_backslash_windows.py`. Reopens [[MYLA-613]]. Decision 6
- [ ] **H9**: `http.json_body` exposes std.json's quadratic number parse: 64,000 digits in 11.7 s, four 300 kB bodies stop a server. `router_json_number_dos.py`, `json_number_time.my`
- [ ] **M14**: `/files/{p:path}/meta` answers `/files/a/b`; `{id:integer}` matches `abc`; malformed patterns are taken silently. `router_path_not_last.my`
- [ ] Low: `static_files` serves `.env` and follows symlinks out of the root; a FIFO blocks a worker; a whole file is read into memory (decision 6: regular files under the resolved root only, no dot files by default, streamed)
