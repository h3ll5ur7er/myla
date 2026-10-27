---
id: MYLA-95
title: Git dependencies and myla fetch
type: feature
status: backlog
priority: medium
labels: [tooling, cli, selfhost]
---
Step 6 of the project tool ([[MYLA-64]]): dependencies from Git, pinned by `myla.lock` and checked out in `.myla/deps/<name>-<commit>/`, as the sections "The lock file" and "Git" of [[Architecture/Project-tool]] describe. Needs [[MYLA-94]].

- [ ] Run Git through `std.process` (`/usr/bin/env git …`); a clear error when it is missing or fails (its stderr, the dependency's name and URL)
- [ ] Resolve `tag` (annotated or not), `branch` and the default branch with `git ls-remote`; take `rev` as given and check it at checkout
- [ ] Check out into `<name>-<commit>.partial`, then rename; remove a stale `.partial` first (question 4, settled)
- [ ] `myla fetch [--update]`: resolve what has no current lock entry (everything with `--update`), check out, write `myla.lock` sorted
- [ ] `build`/`run`/`test`/`check` check out locked commits that are missing and stop on a missing or stale entry (question 1, settled)
- [ ] Tests with local repositories (`git init` in a temporary directory, `file://` URLs): tags, branches, a moved branch with and without `--update`, a dependency of a dependency, two versions of one name, an unknown tag, an interrupted checkout
