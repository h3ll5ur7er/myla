---
id: MYLA-95
title: Git dependencies and myla fetch
type: feature
status: review
priority: medium
labels: [tooling, cli, selfhost]
---
Step 6 of the project tool ([[MYLA-64]]): dependencies from Git, pinned by `myla.lock` and checked out in `.myla/deps/<name>-<commit>/`, as the sections "The lock file" and "Git" of [[Architecture/Project-tool]] describe. Needs [[MYLA-94]].

- [x] Run Git through `std.process` (`/usr/bin/env git …`); a clear error when it is missing or fails (its stderr, the dependency's name and URL)
- [x] Resolve `tag` (annotated or not), `branch` and the default branch with `git ls-remote`; take `rev` as given and check it at checkout
- [x] Check out into `<name>-<commit>.partial`, then rename; remove a stale `.partial` first (question 4, settled)
- [x] `myla fetch [--update]`: resolve what has no current lock entry (everything with `--update`), check out, write `myla.lock` sorted
- [x] `build`/`run`/`test`/`check` check out locked commits that are missing and stop on a missing or stale entry (question 1, settled)
- [x] Tests with local repositories (`git init` in a temporary directory, `file://` URLs): tags, branches, a moved branch with and without `--update`, a dependency of a dependency, two versions of one name, an unknown tag, an interrupted checkout

## How

- **Where:** `selfhost/fetch.my`, used by the project commands (`selfhost/project_cmd.my`). The project model ([[MYLA-93]]) already listed the Git packages without a current lock entry (`Project.unlocked`) and the locked ones not yet checked out (`Project.missing`); this step acts on those lists.
- **Running Git:** git runs as `/usr/bin/env GIT_TERMINAL_PROMPT=0 git …`, so it is found on PATH and inherits the user's environment, and a missing credential fails instead of waiting for a password. Exit status 127 (env didn't find git) reads "git is not installed".
- **References:** `git ls-remote <url>` with `refs/tags/<t>` and `refs/tags/<t>^{}` (the peeled line wins, so an annotated tag gives its commit, not the tag object), `refs/heads/<b>`, or `HEAD`. A `rev` is taken as it is and checked when it is checked out.
- **Checkout:** `git clone --quiet` into `<dir>.partial`, then `git -C … checkout --quiet --detach <commit>`, then `mv` to `.myla/deps/<name>-<commit>`. A stale `.partial` is removed first, and a failed step removes the partial clone. `fetching <name><ref> (<short commit>)` goes to stderr, so a program's output stays clean.
- **`myla fetch [--update]`:** starts from the lock file (from nothing with `--update`), then repeats until nothing is left: resolve, record the commits, check out what's missing. Each round can reveal the Git dependencies of a dependency it just checked out. At the end it writes `render_lock(lock_of(p))`, which keeps only the current entries, sorted. A build without Git dependencies and without a lock file gets none.
- **The other commands:** `build`, `run`, `test` and `check` go through `checked_out_project`, which checks out `missing` and resolves again. They never resolve references: an unlocked dependency stays the model's error ``dependency 'x' is not locked: run `myla fetch` `` (settled question 1).

## Evidence

- **Tests first:** `tests/burn/test_project_fetch.py`, 8 tests with local repositories (`git init`, `file://` URLs). All failed before (`unknown command 'fetch'`) and pass after:
  - a lightweight tag, then an annotated one (the lock holds `git rev-parse v2^{commit}`, and the old entry is gone);
  - a branch that moves only with `--update`;
  - the default branch and a `rev`;
  - `build` checking out a locked commit after `.myla/` was removed, with a stale `.partial` holding junk;
  - `clean --deps`;
  - a dependency of a dependency (two lock entries, sorted; the program prints `deep!`);
  - errors: an unknown tag, a repository that doesn't exist, a commit that doesn't exist (nothing left under `.myla/deps/`), two versions of a package;
  - no lock file without Git dependencies.
- **Network:** `test_project_commands.py`'s Git test now uses a `file://` path that doesn't exist, so no test touches the network.
- **Unit tests:** the `#test` cases of `short`, `lines`, `split_tab` and `trim_end` pass.
