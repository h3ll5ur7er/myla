---
id: MYLA-338
title: Stream traits, memory streams and buffering
type: feature
status: backlog
priority: medium
labels: [stdlib, io, streams, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #41. The base of the streams in waves 3 and 4. A design note goes on the task before code: Myla has no references, so a stream is held in a `var` and an adapter owns the stream it wraps (`Buffered<R: Read>`, `Gzip<R: Read>`).

- **Owns:** `lib/std/io.my`, `docs/Language/Standard-library/Io.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `Read`, `Write`, `Seek` traits; `MemoryStream` (bytes and a cursor)
- [ ] `Buffered<R>` and `BufferedWriter<W>` generic over them; today's `Reader` expressed as one, its API unchanged
- [ ] `copy(r, w)` and `read_to_end` on any `Read`
- [ ] Async forms where today's reader has them
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
