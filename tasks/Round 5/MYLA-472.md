---
id: MYLA-472
title: "std.http: a gzip or deflate body is decoded without a limit"
type: bug
status: todo
priority: medium
labels: [std, http, compress, round-5]
---
Found by [[MYLA-423]], which gave `compress.gunzip`, `zlib_decompress` and `inflate` a `max_output`. `decode_body` in `lib/std/http.my` (P8's file) calls them without one, once for each coding of `Content-Encoding`, so a response (or a request a server decodes) of a few kilobytes that stands for gigabytes is decoded whole: a decompression bomb takes the program's memory, past any body limit the caller set, which applies to the encoded bytes. `Content-Encoding: gzip, gzip` multiplies it.

Reproduction: a body of 1 MB, `gzip -9` of 1 GiB of zeros (Python: `c = zlib.compressobj(9, zlib.DEFLATED, 31)`, then `b"".join(c.compress(bytes(1 << 20)) for _ in range(1024)) + c.flush()`), sent with `Content-Encoding: gzip` to a client that decodes it: the process asks for over 1 GiB. Under a 256 MiB address-space limit `compress.gunzip(body)` fails with `runtime error: out of memory`; `compress.gunzip(body, 1 << 20)` gives `TooLarge` in 0.01 s.

- [ ] `decode_body` passes the most it takes (the caller's body limit, or a default) as `max_output` to each step, and `TooLarge` is an `HttpError` of its own
- [ ] A case with the bomb above, and one with two codings
