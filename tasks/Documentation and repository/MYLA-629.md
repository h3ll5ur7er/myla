---
id: MYLA-629
title: "Seeds updated only when needed; CI publishes the seeds and the tools as artifacts"
type: improvement
status: review
priority: medium
labels: [bootstrap, ci, seeds]
---
The owner's decision (2026-11-13), before Windows adds a third seed: a seed is updated only when it can no longer bootstrap the sources, not in every pull request (supersedes D156's one seed per pull request), and CI publishes each master commit's seeds and tools as workflow artifacts, which tagged releases can replace later. Discussed against the alternatives (seeds only in releases or artifacts, pinned by a lock file; always the latest release; the status quo): the seeds stay in the repository, since artifacts expire (90 days at most on a public repository) and need a token to download, and a commit must bootstrap from what it carries.

- [x] `scripts/check-seed.sh` asks whether the seeds bootstrap the sources (stage 0 to 3 from the machine's seed, the fixed point), not whether they are the current compiler; `selfhost/embedded_std.my` stays required current; a seed older than the sources is reported, not refused
- [x] A seed that can't bootstrap the sources fails with what to do: `scripts/update-seed.sh`, and a `Stage:` commit when the compiler or the library starts using something the seed doesn't know (as D156's exception did)
- [x] `scripts/update-seed.sh --out DIR` writes the seeds of the current sources to `DIR`, leaving `bootstrap/` alone (for the artifacts)
- [x] CI: on a push to master, the bootstrap job uploads the seeds of every target and the x86-64 `myla` and `myla-lsp`, the arm64 job the aarch64 `myla` and `myla-lsp`, kept 90 days
- [x] The pre-push hook, `AGENTS.md`'s working agreement, [[Development/Bootstrap]], [[Development/Conventions]], [[Development/Testing]] and the `myla` skill say the new rule; the decision row (D207), D156 marked superseded
- [x] Evidence: the current seed passes; a seed older than the sources that still bootstraps them passes and is reported older; a seed that can't bootstrap them fails with the message

## What changed

- **`scripts/check-seed.sh`** bootstraps from this machine's seed (or takes a bootstrap's `BUILD_DIR`) and fails with exit 2 and what to do when the seed can't build the sources or reach the fixed point; exit 1 when `selfhost/embedded_std.my` differs from the commit; then reports, for each seed, whether it is the current compiler or an older one and from which commit, without failing.
- **`scripts/bootstrap.sh`** says the same when a stage the seed builds fails (an `ERR` trap over stages 0 to 3, with `set -E` so it reaches `run_tool` and `asm_to_bin`).
- **`scripts/update-seed.sh --out DIR`** writes the seeds of the current sources to `DIR`, their headers still naming `bootstrap/seed*.s` and the commit; `bootstrap/` is untouched. Its comment says when to run it now.
- **CI** (`.github/workflows/ci.yml`): the bootstrap steps say what they check; on a push to master the `bootstrap` job uploads `myla-seeds-<sha>` (both seeds, by `update-seed.sh --out`) and `myla-x86_64-linux-<sha>` (a tarball of `myla` and `myla-lsp`, which keeps the executable bit an artifact's zip drops), the `bootstrap-arm64` job `myla-aarch64-linux-<sha>`, each kept 90 days, the most a public repository allows.
- **The rule:** D207 in [[Project/Decisions]], D156 marked superseded; `AGENTS.md`'s working agreement, [[Development/Bootstrap]], [[Development/Conventions]], [[Development/Testing]], [[Project/Standard-library-roadmap]]'s process, the pre-push hook, `scripts/install-hooks.sh` and the `myla` skill (`SKILL.md`, `reference/compiler.md`, `reference/toolchain.md`, both copies identical).
- **No permanent test** of an older seed: which older seed still builds the sources changes with every commit that needs a new one, so such a test would break by design; the four cases below were run by hand.

## Evidence

Run on master at `ff4ee86` with the new scripts, in a scratch worktree (2026-11-13):

1. **The current seed:** `check-seed.sh` exits 0: "bootstraps these sources (the fixed point)", "bootstrap/seed.s is the current compiler", the same for `seed-aarch64.s`.
2. **An older seed that still builds the sources** (one error message changed in `selfhost/checker.my`, so the compiler's output differs from the seed): the new `check-seed.sh` exits 0 and reports both seeds as "an older compiler (from commit 657881f…); kept until it can't bootstrap the sources (D207)"; the old one exits 1, "run scripts/update-seed.sh and commit bootstrap/seed.s bootstrap/seed-aarch64.s".
3. **A seed that can't build the sources** (the seed of `aef0b21`, before `#track_caller`, against today's library): `bootstrap.sh` exits 1 after the type errors (`unknown attribute '#track_caller'`) with "FAIL: bootstrap/seed.s can't build these sources; if they use something it doesn't know (a primitive, a runtime variable, an attribute), run scripts/update-seed.sh and commit the seeds, as a `Stage:` commit before that use (D207)", printed once (before `set -E` the trap didn't reach the failing command inside `run_tool`, and printed nothing); `check-seed.sh` exits 2 with its own form of it.
4. **`update-seed.sh --out build/art`** writes `seed.s` (13,277,767 bytes) and `seed-aarch64.s` (28,503,027 bytes), headed `# bootstrap/seed.s: …` and "from commit ff4ee86…"; `git status bootstrap/` is clean.

On the branch: `scripts/bootstrap.sh` reaches the fixed point with no hint printed, and `scripts/check-seed.sh build` exits 0 with both seeds current. The workflow parses as YAML; the artifact steps run only on a push to master, so the first master commit after the merge is their test.
