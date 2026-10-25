---
id: MYLA-31
title: Missing stdlib root makes std imports resolve to /std
type: bug
status: backlog
priority: low
labels: [selfhost, scripts]
---
Without the second argument, `std.*` resolves to `/std/…` (`gen_main: cannot read module: /std/io.my`). [[scripts/build.sh]] calls `./build/stage3 "$input"` without a stdlib root, so `scripts/build.sh` and `scripts/run.sh` fail for every program that imports `std`.

## Done when

- [ ] `scripts/build.sh` passes `src/myla` (or the compiler derives a default from its own location / an environment variable)
- [ ] An error message that names the missing root
