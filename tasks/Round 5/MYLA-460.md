---
id: MYLA-460
title: "std.xml's stream reader is quadratic in an event's length over short reads"
type: bug
status: backlog
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

- [ ] Read a failed event again only once the bytes after it could end it (`std.csv` scans them with a small state machine for the record's end, [[Language/Standard-library/Csv#Reading a stream]]), or once they at least doubled, and gather the reads in between in a builder instead of copying the tail each time
- [ ] A case over `io.short_reads` with an event of 250,000 bytes, as `std.csv`'s `stream_holds_a_chunk` has
