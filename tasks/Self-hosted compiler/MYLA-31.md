---
id: MYLA-31
title: Missing stdlib root makes std imports resolve to /std
type: bug
status: done
priority: low
labels: [selfhost, scripts]
---
Without the second argument, `std.*` resolves to `/std/…` (`gen_main: cannot read module: /std/io.my`). [[scripts/build.sh]] calls `./build/stage3 "$input"` without a stdlib root, so `scripts/build.sh` and `scripts/run.sh` fail for every program that imports `std`.

## Done when

- [x] `scripts/build.sh` passes `src/myla` (or the compiler derives a default from its own location / an environment variable)
- [x] An error message that names the missing root

## How

`default_stdlib_root(argv0)` in [[selfhost/loader.my]]: `src/myla` next to the `build/` directory the tool is in (`<dir of argv[0]>/../src/myla`), plain `src/myla` when argv[0] has no directory part. `gen_main` (so `build/stage3`) and the CLI use it when no root is given; [[scripts/build.sh]] passes `<repo>/src/myla` explicitly and works from any directory. When `std.*` can't be resolved because no root was given, the error says so: `cannot resolve import 'std.io': no standard library root was given`.

## Evidence

[[tests/burn/test_selfhost_cli.py]] builds the CLI into `<tmp>/build/myla` next to a `<tmp>/src/myla` link and runs it from another directory: before, `module error: cannot resolve import 'std.process'` for every command; after, all four tests pass (and `--stdlib /nowhere` gives the plain resolve error). `build/myla run examples/stdio/…` works from `/tmp`.
