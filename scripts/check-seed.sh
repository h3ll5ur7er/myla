#!/usr/bin/env bash
#
# check-seed.sh — do the seeds bootstrap these sources? (MYLA-218, D127, D207)
#
# A seed needn't be the compiler of the sources it is committed with (D207,
# which replaced D156's seed in every pull request): it must bootstrap them,
# stage 0 (the seed) building stage 1, the current compiler, and stages 2 and
# 3 at the byte-identical fixed point. A seed is updated (scripts/update-seed.sh)
# only when it no longer can: when the compiler or the standard library it
# imports starts using something the seed doesn't know (a primitive, a
# runtime variable, an attribute), in a `Stage:` commit before that use.
# This machine's seed is checked here; the other targets' seeds by CI on
# their own machine (the bootstrap-arm64 job for bootstrap/seed-aarch64.s).
# Whether each seed is also the current compiler is reported, not required.
#
# selfhost/embedded_std.my, the standard library the tools carry (MYLA-243),
# must match lib/: the bootstrap rewrites it, and a difference from the
# commit fails.
#
# CI's bootstrap jobs run this on every pull request; the optional pre-push
# hook (.githooks/pre-push, scripts/install-hooks.sh) runs it before a push.
#
# Usage:
#   scripts/check-seed.sh [BUILD_DIR]
#
# With BUILD_DIR holding a bootstrap's stage3 and stage3.s (scripts/bootstrap.sh
# BUILD_DIR, which fails itself when the seed can't bootstrap the sources),
# those are used; otherwise stages 0–3 run from this machine's seed into
# build/seed-check, the fixed point included.
#
# Exit status: 0 when the seed bootstraps the sources and the embedded
# library is current; 1 when the embedded library differs from the commit
# (commit it); 2 when the seed can't bootstrap the sources (run
# scripts/update-seed.sh and commit the seeds).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

. scripts/host.sh
SEED="$HOST_SEED"
ENTRY="selfhost/gen_main.my"
STDLIB_ROOT="lib"

update_hint() {
    echo "check-seed: $SEED can't bootstrap these sources: run scripts/update-seed.sh and commit the seeds (D207; as a \`Stage:\` commit when the sources start using something the seed doesn't know, before that use)" >&2
}

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
        update_hint
        exit 2
    fi
    if ! cmp -s "$out/stage2.s" "$out/stage3.s"; then
        echo "check-seed: no fixed point (stage2.s and stage3.s differ); scripts/bootstrap.sh shows where" >&2
        update_hint
        exit 2
    fi
    stage3="$out/stage3.s"
    compiler="$out/stage2"
fi
echo "check-seed: $SEED bootstraps these sources (the fixed point)"

# the standard library the toolchain carries (MYLA-243): the bootstrap writes
# selfhost/embedded_std.my from lib/, so after one it differs from the commit
# when the committed module is older than lib/
EMBEDDED="selfhost/embedded_std.my"
if git rev-parse --verify -q HEAD > /dev/null 2>&1 && ! git diff --quiet HEAD -- "$EMBEDDED"; then
    echo "check-seed: $EMBEDDED differs from the commit: the bootstrap wrote it from lib/; commit it" >&2
    exit 1
fi

# whether each seed is also the current compiler (its assembly, everything
# after its header of comment lines, against the compiler's output for its
# target): reported only (D207)
for entry in $SEEDS; do
    target="${entry%%:*}"
    seed="${entry#*:}"
    want="$(dirname "$stage3")/check-$target.s"
    if ! seed_compile "$compiler" "$target" "$want"; then
        echo "check-seed: the compiler failed to build itself for $target" >&2
        exit 2
    fi
    from="$(sed -n 's/^# fixed point, from \(.*\), without the embedded standard library$/\1/p' "$seed" 2>/dev/null | head -1 || true)"
    if [ -f "$seed" ] && awk 'f || !/^#/ { f = 1; print }' "$seed" | cmp -s - "$want"; then
        echo "check-seed: $seed is the current compiler"
    else
        echo "check-seed: $seed is an older compiler${from:+ (from $from)}; kept until it can't bootstrap the sources (D207)"
    fi
done
exit 0
