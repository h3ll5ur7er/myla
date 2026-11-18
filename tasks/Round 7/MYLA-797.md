---
id: MYLA-797
title: "R7-8 XML stream reader: a cut multi-byte character (H10), the quadratic DOCTYPE"
type: bug
status: review
priority: high
labels: [xml, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "XML" (section 5). Files: `lib/std/xml.my`. The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. No owner's decision. New tasks it files take ids 857–860.

- [x] **H10** (high, old remnant): pieces `<s>Gruesse aus K` + the first byte of `ö`, then the rest: `start s`, a blocked read, an error. `repro-r6/library/xml_stream_waits_cut_char.my`. Reopens [[MYLA-460]]
- [x] The fix made a DOCTYPE quadratic over short reads (200 KB: 9.2 s, 26 ms before)
- [x] Low: `<log>value [1]\n` holds back `]\n`

## What changed

All in [[lib/std/xml.my]].

- **H10.** `XmlReader.text`, fed by a stream, failed the whole text when the bytes so far ended inside a character (`char_len` is 0 for a cut sequence, so `InvalidChar`), so the stream reader read the text again from its first byte; `scan_event` takes a text that starts with an ordinary byte for an error (`E_WAIT`), so the reader waited for the bytes to double, past the event. Now `text` stops before a character the end cuts (`char_cut`: a lead byte, only continuation bytes after it, fewer than it needs), as it stops before a `]` or a CR there: the text before it is given, and the scan starts at the cut character (`E_TEXT`: any byte may end it).
- **Low.** `text` held back a `]` that was one of the last two bytes, though the byte after it shows whether a `]]>` can follow. Now it holds back a `]` only at the end, or a `]]` there.
- **The quadratic DOCTYPE.** `scan_event` took any `>` of a DOCTYPE for its possible end, so a long internal subset over short reads was lexed again at every declaration. Its states now follow `doctype` and `subset`: the literals after SYSTEM and PUBLIC, the subset's declarations with their quoted values, its comments and processing instructions, `%name;` and the `]`; only a `>` outside all of them may end the DOCTYPE (15 new states, `E_DECL_DQ` to `E_SUB_SQ`; `E_FOUND` is 64 now).
- **Found on the way ([[MYLA-857]]):** `fill` dropped the bytes read before a read that failed in the same pass, so a `read_event` called again after an `Io` error went on with a gap. It keeps them now.
- **Tests.** `stream_every_cut` is the generator the lane asked for: a stream `Pieces` gives a document in parts and fails once after each (a read that would block), and after each failure the events given so far must be what the text reader gives of the bytes read (`events_by`: every event they hold, and of a text they cut what is sure, `text_held`); at the end, every event. Seven documents (every kind of event; H10's; the Low item's; a DOCTYPE whose literals, subset, comment and PI hold `>`, `]` and quotes; multi-byte names, values and references), each cut in two at every byte and in pieces of every size from 1 to its length. `stream_work_is_linear` is the timing guard that doesn't depend on load: `XmlStreamReader.work` counts the bytes the fills gather (each is lexed again), and a 4,000-byte event of each kind over reads of 1 and of 1 to 16 bytes must stay below four times the document (the doubling reads make it at most three; one read in one piece makes it one).

## Evidence

Before: the base (`e659342`) with the new cases grafted in (and the counter `work`), and a temporary case reporting each document's first failure:

- `FAIL stream_every_cut: … cut at 79: after 79 bytes decl 1.0  |doctype r [<!ENTITY x 'y'>]|start r a=1€ , not …|start r a=1€ |text t\n` (H10 in the first document: byte 79 cuts the `ü` after `t\r\n`)
- H10's document cut at 17: `after 17 bytes start s, not start s|text Gruesse aus K`
- The Low item's cut at 15: `after 15 bytes start log|text value [1, not start log|text value [1]\n`
- `FAIL stream_work_is_linear: runtime error: doctype in reads of 1 to 1: 540166 bytes lexed for 4009` (every other kind: 8,013 to 12,585 bytes)

After: all six stream cases pass. The work of each kind, 4,000 bytes, reads of 1 / 1 to 16 / one piece: attr 8,104 / 8,089 / 4,009; comment 8,115 / 8,070 / 4,014; doctype 8,107 / 8,089 / 4,009 (540,166 / 506,009 before); tagquotes 12,585 / 12,570 / 4,394; text 8,013 / 4,457 / 4,007.

The review's reproducers, interpreted and natively the same:

- `xml_stream_waits_cut_char.my`: `start s`, `text Gruesse aus K`, `text öln`, `start m`, `end m`, then the read that would block (before: `start s`, the blocked read, `error 1:4: the stream failed`).
- `xml_stream_text_bracket_held.my`: `start log`, `text [value [1]\n]`, then the blocked read (before: `text [value [1]`).
- `xml_stream_doctype_quadratic.my`, natively on x86-64, a comparison on one machine in one session (2026-11-18, `e659342` and this branch), reads of 1 byte: doctype 200,000 bytes 7,192 ms before, 12 ms after; 1,000,000 bytes 61 ms. The other kinds at 200,000 bytes stay 10 to 30 ms (attr 20, comment 19, cdata 20, pi 10, tagquotes 29, text 30, ref 11).

Suites:

- `build/myla test lib/std/xml.my --stdlib lib`: 118/118 interpreted (16 s; `stream_every_cut` 6 s), `--native`, `--target aarch64-linux`, `--target wasm32-wasi`.
- `tests.burn.test_xml` OK.
- `scripts/test.sh fast`: 1,058 tests OK (7 skipped); `scripts/test.sh`: 1,836 tests OK (390 skipped), on the branch's tip.
- `scripts/bootstrap.sh`: byte-identical fixed point; `scripts/check-seed.sh`: the seed bootstraps the sources (the embedded library committed with the change).

## Proposals

See [[MYLA-857]]: whether `read_event` may be called again after an `Io` error. Built: yes.
