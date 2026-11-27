---
id: MYLA-888
title: "test_windows and windows-runner's --wine runs read programs' output through pipes Wine's services may hold"
type: bug
status: todo
priority: low
labels: [windows, wine, testing]
---
Found by [[MYLA-759]]: the first program of a Wine server starts the prefix's services, which hold its standard error as long as the server lives, so a test that reads the program's output through pipes waits for them. `_native.run_argv` and `scripts/test-target.py`'s `MYLA_EMULATOR` now run programs behind `tests/burn/_wine_run.py`, which ends with the program. `tests/burn/test_windows.py` still runs most of its programs with `[*wine(), …]` and `capture_output`, and `scripts/windows-runner.py run --wine` with Wine alone. Both start the services quietly first (`wine_env`), so they only meet it when the server is started again meanwhile: a pause past `wine_env`'s 60 s in a plain `unittest` run, or another run on the same prefix stopping its server.

- [ ] test_windows' runs through `wine_run()` where they read a program's output (not where a test reads the program's own `/proc`, which `wine_run` keeps: it `exec`s the program)
- [ ] windows-runner's `--wine` runs the same way, or its prefix's server checked before each case
