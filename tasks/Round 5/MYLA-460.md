---
id: MYLA-460
title: "std.xml's stream reader is quadratic in an event's length over short reads"
type: bug
status: review
priority: medium
labels: [std, xml, streams, round-5]
---
Found by [[MYLA-420]] (P6), which fixed the same shape in `std.io`'s `Buffered` and `std.csv`'s stream reader (the review's M17). `XmlStreamReader.read_event` reads an event again after each `fill` while it fails at the end of the bytes read, and `fill` copies the bytes not yet used before the new ones. The reads double (`chunk`), but a stream that gives few bytes a read whatever is asked (a pipe, a socket, a decompressor; `io.short_reads`) makes a long event quadratic. Natively on x86-64 (2026-11-10), a tag with one long attribute over 16-byte reads:

| Attribute | Time |
| --- | --- |
| 25,000 bytes | 60 ms |
| 50,000 bytes | 178 ms |
| 100,000 bytes | 555 ms |

```myla
import std.io as io
import std.xml as xml
from std.xml import Event

fun main() {
    var sb = StringBuilder()
    sb.append("<a v=\"")
    var i = 0
    while i < 100000 {
        sb.append_byte('q')
        i += 1
    }
    sb.append("\"/>")
    var r = xml.stream_reader(io.short_reads(io.from_str(sb.build()), 16))
    while true {
        match r.read_event() {
            Ok(Eof) => { break }
            Ok(_) => {}
            Err(e) => {
                print(f"{e}")
                break
            }
        }
    }
}
```

- [x] Read a failed event again only once the bytes after it could end it (`std.csv` scans them with a small state machine for the record's end, [[Language/Standard-library/Csv#Reading a stream]]), or once they at least doubled, and gather the reads in between in a builder instead of copying the tail each time
- [x] A case over `io.short_reads` with an event of 250,000 bytes, as `std.csv`'s `stream_holds_a_chunk` has

Taken into [[MYLA-424]] (P10), whose file `lib/std/xml.my` is.

## What changed

`XmlStreamReader.fill` ([[lib/std/xml.my]]) used to read once and copy the unused tail before the new bytes, and `read_event` lexed the failed event again after every read. Now `fill` reads until the bytes it adds at least match the tail it holds back (or the stream ends), gathering the reads in one `StringBuilder`: the second of the two ways the first box names ("or once they at least doubled"). A long event is then lexed again a logarithmic number of times, and each byte is copied a logarithmic number of times; the reads still ask for `chunk` bytes, which doubles while an event needs more and goes back to 64 KiB after one. A failing stream's `Io` error keeps its position (where the tail starts). The case uses the module's own short-read stream, `Trickle` (1 to `most` bytes a read), rather than P6's `io.short_reads`, which this lane's base doesn't have.

## Evidence

- The case first: `stream_long_event` reads a tag with a 250,000-byte attribute and 1000 bytes of text over reads of 1 to 16 bytes. With the old `fill` it passes natively but in 6.7 s (with the new one, 0.3 s, the build included).
- The task's reproduction (one read of 16 bytes at a time, natively, x86-64, `time.now_ms` around the reading):

| Attribute | Before | After |
| --- | --- | --- |
| 25,000 bytes | 29 ms | 0 ms |
| 50,000 bytes | 110 ms | 1 ms |
| 100,000 bytes | 565 ms | 1 ms |
| 250,000 bytes | 2,870 ms | 2 ms |
| 1,000,000 bytes | 49,276 ms | 10 ms |

- `build/myla test lib/std/xml.my --stdlib lib`: 90/90 interpreted, `--native`, `--target aarch64-linux`, `--target wasm32-wasi` (the `streams` case still reads every document in pieces of 1, 2, 3, 7 and 64 bytes as the text reader does, ISO-8859-1 in pieces of 1 to 23). `test_xml` (expat and the W3C suite, the stream reader in pieces of 1 to 7 bytes for every document) OK.

## Review 2026-11-12

Reopened ([[Project/Review-2026-11-12]]): the fix for the quadratic scan made the reader wait for bytes it doesn't need (new, high).

- [x] **The stream reader holds back a complete event until more bytes arrive.** `XmlStreamReader.fill` (`xml.my:1474`) reads until new bytes match the tail it held back, so an event that is whole in the buffer is given only after the next read: on a pipe an event complete at 1.0 s is delivered at 5.0 s, and a read that would block turns into `error 1:4: the stream failed` before `<m/>` is given (`repro-r5/std/bug_xml_stream_waits2.my`: pieces `<s><m v="0000000000` and `"/>`; before the fix the reader gave `start s`, `start m`, `end m`). Scan for the event's possible end, as `std.csv` does
- [x] A case that fails if the reader reads again once an event is whole

### What changed (round 6)

`fill` ([[lib/std/xml.my]]) now stops reading as soon as the bytes it read may end the event that failed, not only once they match the held-back tail. `scan_event`, a small state machine like `std.csv`'s `scan_record`, follows the event from its first byte: a tag's `>` outside quotes, a comment's `-->`, a CDATA section's `]]>`, a processing instruction's `?>` (the declaration's too), any `>` of a DOCTYPE, a reference's `;`, and any byte after a text cut in a character, a CR or a `]`. It finds a superset of the places a well-formed event can end (a malformed one waits for the end of the stream anyway), so the reader never waits for bytes an event doesn't need; an end inside the held-back tail is ignored, as it didn't end the event. Its state is kept between fills of one event, so each byte is scanned once. The doubling rule stays, so a long event is still lexed a logarithmic number of times. The reader also no longer waits for a fourth byte at the stream's start: only while the bytes may still be cut in a byte order mark or a UTF-16 mark (`mark_cut`), so `<s>` and then a blocking read gives `start s`.

### Evidence (round 6)

- The case first: `stream_gives_whole_events` reads 14 documents, each over a stream that fails right after its first part (`Trickle`'s `fail_at`, which now also caps a read at it), in pieces of 1, 2, 3, 7 and 64 bytes, and wants every event whole in that part before the `Io` error: a tag with quotes holding `>` and `'>`, an empty element, a comment with `->` and `- `, an empty comment, a PI with `>` and `??>`, a CDATA section ending in `]]]]>`, a DOCTYPE whose subset holds `'y>'` and `<!-- ]> -->`, references, CRLF, `é]` in text, a BOM, `<s>` alone, and a closed root. Before: `FAIL stream_gives_whole_events: <s><m v="0000000000"/> in pieces of 1: start s|error 1:4: the stream failed`; after, it passes, with `scan_event`'s 10 and `mark_cut`'s 5 cases.
- The review's reproductions: `bug_xml_stream_waits2.my` gives `start s`, `start m`, `end m`, then the blocked read (before: `start s`, the blocked read, `error 1:4`). On a pipe (`bug_xml_stream_waits.my`, native): `<m/>` at 1003 ms, `</s>` at 6008 ms (before: all three at 6009 ms).
- Still linear (the task's reproduction, native, x86-64, 16-byte reads): 25,000 bytes 1 ms, 100,000 2 ms, 250,000 6 ms, 1,000,000 21 ms (the round-5 reader: 1, 1, 4, 20 ms).
- `build/myla test lib/std/xml.my --stdlib lib`: 106/106 interpreted (9 s, was 6 s: the scan is a loop over each byte read, which the interpreter runs at about 2 µs a byte), `--native` (checked), `--target aarch64-linux`, `--target wasm32-wasi`. `tests.burn.test_xml` OK.
- `scripts/test.sh` once at the end of the lane (with [[MYLA-550]]): 1,549 tests; the three failures are the embedded library (behind `lib/` until the seed commit, twice) and `test_children_run_in_parallel`, which passes alone. Bootstrap fixed point byte-identical.
