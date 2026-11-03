#!/usr/bin/env bash
#
# check-seed.sh — is bootstrap/seed.s the current compiler? (MYLA-218)
#
# The seed must be the self-hosted compiler of the sources it is committed
# with: its assembly equal to the stage3.s of a bootstrap of those sources.
# CI's bootstrap job runs this on every pull request; the optional pre-push
# hook (.githooks/pre-push, scripts/install-hooks.sh) runs it before a push.
#
# Usage:
#   scripts/check-seed.sh [BUILD_DIR]
#
# With BUILD_DIR holding a bootstrap's stage3.s (scripts/bootstrap.sh
# BUILD_DIR), that one is compared; otherwise stages 0–3 run from the seed into
# build/seed-check (about 5 s), the fixed point included.
#
# Exit status: 0 when the seed is current, 1 when it isn't (run
# scripts/update-seed.sh and commit bootstrap/seed.s) or when the bootstrap
# rewrote selfhost/embedded_std.my (commit it too), 2 on a failed bootstrap.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SEED="bootstrap/seed.s"
ENTRY="selfhost/gen_main.my"
STDLIB_ROOT="lib"

asm_to_bin() {  # <src.s> <out-bin>
    as --64 -o "${2}.o" "$1"
    ld -o "$2" "${2}.o"
}

stage3=""
if [ $# -gt 0 ] && [ -f "$1/stage3.s" ]; then
    stage3="$1/stage3.s"
else
    out="build/seed-check"
    mkdir -p "$out"
    if ! {
        asm_to_bin "$SEED" "$out/stage0" &&
        "$out/stage0" "$ENTRY" "$STDLIB_ROOT" > "$out/stage1.s" && asm_to_bin "$out/stage1.s" "$out/stage1" &&
        "$out/stage1" "$ENTRY" "$STDLIB_ROOT" > "$out/stage2.s" && asm_to_bin "$out/stage2.s" "$out/stage2" &&
        "$out/stage2" "$ENTRY" "$STDLIB_ROOT" > "$out/stage3.s"
    }; then
        echo "check-seed: the bootstrap from $SEED failed" >&2
        exit 2
    fi
    if ! cmp -s "$out/stage2.s" "$out/stage3.s"; then
        echo "check-seed: no fixed point (stage2.s and stage3.s differ); scripts/bootstrap.sh shows where" >&2
        exit 2
    fi
    stage3="$out/stage3.s"
fi

# the standard library the toolchain carries (MYLA-243): the bootstrap writes
# selfhost/embedded_std.my from lib/, so after one it differs from the commit
# when the committed module is older than lib/
EMBEDDED="selfhost/embedded_std.my"
if git rev-parse --verify -q HEAD > /dev/null 2>&1 && ! git diff --quiet HEAD -- "$EMBEDDED"; then
    echo "check-seed: $EMBEDDED differs from the commit: the bootstrap wrote it from lib/; commit it (with scripts/update-seed.sh's seed)" >&2
    exit 1
fi

# the seed's assembly: everything after its header of comment lines
if awk 'f || !/^#/ { f = 1; print }' "$SEED" | cmp -s - "$stage3"; then
    echo "check-seed: $SEED is the current compiler"
    exit 0
fi
echo "check-seed: $SEED is not the compiler of these sources: run scripts/update-seed.sh and commit $SEED" >&2
exit 1
