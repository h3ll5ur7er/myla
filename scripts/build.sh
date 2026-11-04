#!/usr/bin/env bash
# build.sh <source.my> [out]: compile with the self-hosted compiler (run
# scripts/bootstrap.sh first). Works from any directory.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
input="$1"
out="${2:-a.out}"
obj="$(mktemp --suffix=.o)"

trap 'rm -f "$obj"' EXIT

# for this machine, stage3's default target, with its as and ld (MYLA-276)
flags=()
if [ "$(uname -m)" = x86_64 ]; then flags=(--64); fi
"$repo/build/stage3" "$input" "$repo/lib" | as "${flags[@]}" -o "$obj" -
ld -o "$out" "$obj"
