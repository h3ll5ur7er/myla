---
id: MYLA-339
title: File streams and temporary files
type: feature
status: backlog
priority: medium
labels: [stdlib, fs, streams, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #42, #45. Files bigger than memory.

- **Owns:** `lib/std/fs.my`, `docs/Language/Standard-library/Fs.md`
- **Needs:** [[MYLA-336]], [[MYLA-338]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `File` (`open` with modes, `create`, `append`) implementing `Read`, `Write` and `Seek`; `len`, `flush`, `close`, closing when it goes out of scope if the language allows, else explicit
- [ ] `metadata(path)`: size, kind, permissions, modification time
- [ ] Temporary files and directories under `$TMPDIR`; `std.test.temp_dir` built on them
- [ ] A 4 GB file copied with a 1 MB buffer on x86-64 in constant memory
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
