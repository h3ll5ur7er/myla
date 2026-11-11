---
id: MYLA-472
title: "std.http: a gzip or deflate body is decoded without a limit"
type: bug
status: review
priority: medium
labels: [std, http, compress, round-5]
---
Found by [[MYLA-423]], which gave `compress.gunzip`, `zlib_decompress` and `inflate` a `max_output`. `decode_body` in `lib/std/http.my` (P8's file) calls them without one, once for each coding of `Content-Encoding`, so a response (or a request a server decodes) of a few kilobytes that stands for gigabytes is decoded whole: a decompression bomb takes the program's memory, past any body limit the caller set, which applies to the encoded bytes. `Content-Encoding: gzip, gzip` multiplies it.

Reproduction: a body of 1 MB, `gzip -9` of 1 GiB of zeros (Python: `c = zlib.compressobj(9, zlib.DEFLATED, 31)`, then `b"".join(c.compress(bytes(1 << 20)) for _ in range(1024)) + c.flush()`), sent with `Content-Encoding: gzip` to a client that decodes it: the process asks for over 1 GiB. Under a 256 MiB address-space limit `compress.gunzip(body)` fails with `runtime error: out of memory`; `compress.gunzip(body, 1 << 20)` gives `TooLarge` in 0.01 s.

- [x] `decode_body` passes the most it takes (the caller's body limit, or a default) as `max_output` to each step, and `TooLarge` is an `HttpError` of its own
- [x] A case with the bomb above, and one with two codings

Taken into [[MYLA-422]] (lane P8), on P9's `max_output` (commit c3dc460 cherry-picked).

## Evidence

- `decode_body(h, body, max)` passes `max` to `gunzip`, `zlib_decompress` and the raw `inflate` fallback at each step; the client gives it the request's `max_body_bytes` (`with_limits`, 1 GiB by default). `CompressError.TooLarge` is `HttpError.BodyTooLarge` (the body's own error: "body too large"), and a zlib body past the limit doesn't fall back to raw DEFLATE.
- Test first: `content_codings` gained 64 KiB of zeros as gzip, zlib, raw deflate and `gzip, gzip` (each under 4 KiB) decoded with a limit of 4 KiB: before, with the limit passed but not used, `FAIL content_codings: runtime error: gzip: 65536 bytes decoded past the limit`; after, `BodyTooLarge` for each, and each decodes whole at a limit of 64 KiB. `build/myla test lib/std/http.my --stdlib lib`: 221/221.
- `tests.burn.test_http.MylaClient`: a Python endpoint sends 64 MiB of zeros gzipped (65 KB); the Myla client with `with_limits(65536, 1048576)` prints `error: body too large`, interpreted and built. A first version of the test also fetched it with the default limit: the interpreted client grew past 6.4 GB and ran 12 minutes before it was stopped — what a bomb does with a 1 GiB limit in the interpreter, so that line was dropped.

