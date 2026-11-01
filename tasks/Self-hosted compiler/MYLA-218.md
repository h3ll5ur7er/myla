---
id: MYLA-218
title: "The bootstrap from a committed assembly seed"
type: feature
status: todo
priority: high
labels: [bootstrap, selfhost]
---
D101 ([[MYLA-201]]): stage 1 of the bootstrap is built from a committed assembly file, the self-hosted compiler's own output, instead of by the Python toolchain. The stage-3 assembly is 6.2 MB today (626 KB with gzip, about what Git stores per version).

- [ ] `bootstrap/seed.s`: the stage-3 assembly of `selfhost/gen_main.my`, with a header comment naming the commit and the fixed point it came from; `.gitattributes` marks it `-diff linguist-generated`
- [ ] `scripts/bootstrap.sh`: stage 1 from the seed (`as`, `ld`), then stages 2 and 3 and the fixed point as today; the Python stage 1 stays available behind an option until [[MYLA-219]]
- [ ] `scripts/update-seed.sh`: regenerates the seed from a verified fixed point; [[Development/Bootstrap]] says when (before the compiler's own source uses a construct the seed lacks; otherwise at will) and how to check a seed (regenerate and compare)
- [ ] CI: the bootstrap job starts from the seed; the seed is checked to still build the current compiler to the fixed point
- [ ] Measured: the bootstrap's time from the seed against the time from Python
