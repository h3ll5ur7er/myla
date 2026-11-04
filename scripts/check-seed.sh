#!/usr/bin/env bash
#
# check-seed.sh — are the seeds the current compiler? (MYLA-218, D127)
#
# Each seed must be the self-hosted compiler of the sources it is committed
# with: this machine's (bootstrap/seed.s on x86-64, bootstrap/seed-aarch64.s
# on aarch64) equal to the stage3.s of a bootstrap of those sources, the
# other's to what that stage 3 compiler writes for its target (`--target`).
# CI's bootstrap job runs this on every pull request; the optional pre-push
# hook (.githooks/pre-push, scripts/install-hooks.sh) runs it before a push.
#
# Usage:
#   scripts/check-seed.sh [BUILD_DIR]
#
# With BUILD_DIR holding a bootstrap's stage3 and stage3.s (scripts/bootstrap.sh
# BUILD_DIR), those are used; otherwise stages 0–3 run from this machine's
# seed into build/seed-check (about 5 s on x86-64), the fixed point included.
#
# Exit status: 0 when the seed is current, 1 when it isn't (run
# scripts/update-seed.sh and commit the seeds) or when the bootstrap
# rewrote selfhost/embedded_std.my (commit it too), 2 on a failed bootstrap.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

. scripts/host.sh
SEED="$HOST_SEED"
ENTRY="selfhost/gen_main.my"
STDLIB_ROOT="lib"

stage3=""
if [ $# -gt 0 ] && [ -f "$1/stage3.s" ] && [ -x "$1/stage3" ]; then
    stage3="$1/stage3.s"
    compiler="$1/stage3"
else
    out="build/seed-check"
    mkdir -p "$out"
    if ! {
        asm_to_bin "$SEED" "$out/stage0" &&
        run_tool "$out/stage0" "$ENTRY" "$STDLIB_ROOT" > "$out/stage1.s" && asm_to_bin "$out/stage1.s" "$out/stage1" &&
        run_tool "$out/stage1" "$ENTRY" "$STDLIB_ROOT" > "$out/stage2.s" && asm_to_bin "$out/stage2.s" "$out/stage2" &&
        run_tool "$out/stage2" "$ENTRY" "$STDLIB_ROOT" > "$out/stage3.s"
    }; then
        echo "check-seed: the bootstrap from $SEED failed" >&2
        exit 2
    fi
    if ! cmp -s "$out/stage2.s" "$out/stage3.s"; then
        echo "check-seed: no fixed point (stage2.s and stage3.s differ); scripts/bootstrap.sh shows where" >&2
        exit 2
    fi
    stage3="$out/stage3.s"
    compiler="$out/stage2"
fi

# the standard library the toolchain carries (MYLA-243): the bootstrap writes
# selfhost/embedded_std.my from lib/, so after one it differs from the commit
# when the committed module is older than lib/
EMBEDDED="selfhost/embedded_std.my"
if git rev-parse --verify -q HEAD > /dev/null 2>&1 && ! git diff --quiet HEAD -- "$EMBEDDED"; then
    echo "check-seed: $EMBEDDED differs from the commit: the bootstrap wrote it from lib/; commit it (with scripts/update-seed.sh's seed)" >&2
    exit 1
fi

# each seed's assembly (everything after its header of comment lines) against
# the compiler's output for its target
stale=""
for entry in $SEEDS; do
    target="${entry%%:*}"
    seed="${entry#*:}"
    want="$stage3"
    if [ "$target" != "$HOST_TARGET" ]; then
        want="$(dirname "$stage3")/check-$target.s"
        if ! run_tool "$compiler" "$ENTRY" "$STDLIB_ROOT" --target "$target" > "$want"; then
            echo "check-seed: the compiler failed to build itself for $target" >&2
            exit 2
        fi
    fi
    if [ -f "$seed" ] && awk 'f || !/^#/ { f = 1; print }' "$seed" | cmp -s - "$want"; then
        echo "check-seed: $seed is the current compiler"
    else
        echo "check-seed: $seed is not the compiler of these sources" >&2
        stale="$stale $seed"
    fi
done
if [ -n "$stale" ]; then
    echo "check-seed: run scripts/update-seed.sh and commit$stale" >&2
    exit 1
fi
exit 0
