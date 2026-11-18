---
id: MYLA-857
title: "std.xml's stream reader loses the bytes read before a failed read"
type: bug
status: review
priority: medium
labels: [std, xml, streams, round-7]
---
Found by [[MYLA-797]] while testing the stream reader with a failure after every part of a document. `XmlStreamReader.fill` ([[lib/std/xml.my]]) may read several times in one pass (until the bytes may end the event that failed, or match what it held back, [[MYLA-460]]); when a read after the first fails, it returned the `Io` error and dropped the bytes the reads before it had given. A program that calls `read_event` again after such an error (a stream that doesn't wait gives a read that would block, `IoError.Other(11)`, and is read again later) then reads the document with a gap: no error, other events.

To reproduce: a stream that gives `<log>` a byte at a time and fails once after each byte. At the base of round 7 (`e659342`), the reader gave `start l`: the `og` read before the failures in the same pass were lost.

- [x] `fill` keeps what it read before a failed read (the bytes become the reader's, as after a read that succeeds), then gives the `Io` error, so the next `read_event` goes on where it stopped
- [x] A case that reads documents with a failure after every part and wants every event the text reader gives ([[MYLA-797]]'s `stream_every_cut`)
- [x] Say on [[Language/Standard-library/Xml]] that `read_event` may be called again after an `Io` error

## Evidence

- Before (the base's `xml.my` with `stream_every_cut` added, a temporary case reporting each document's first failure): `<log>value [1]\n</log>` in pieces of 1: `after 5 bytes start l, not start log`; `<s><m v="0000000000"/>…` in pieces of 1: `after 22 bytes start s|start m, not start s|start m v=0000000000|end m`; the DOCTYPE document of the case in pieces of 1: nothing given after 112 bytes.
- After: `stream_every_cut` passes (each of its seven documents in pieces of every size, a failure after each), interpreted, natively, on aarch64 and on wasm32; `tests.burn.test_xml` OK.

## Proposals

Accepted by the owner on 2026-11-18 as D293.

Whether a reader may be read again after an `Io` error isn't settled anywhere, and the stream readers differ: `std.csv`'s ends at one on purpose (`CsvStreamReader.fill` sets `done`). Built: `XmlStreamReader.read_event` may be called again and goes on (its iterator still ends after any error, as before), as a read that would block or was interrupted is no end of the stream. Alternatives: (a) an `Io` error ends the XML reader too, as std.csv's (then nothing needs keeping, but a stream that doesn't wait can't be read, and a test can't stop the reader at every byte in one pass); (b) the rule built here for every stream reader, std.csv's included (a change to std.csv, outside this lane). Recommended: (b), as a follow-up.
