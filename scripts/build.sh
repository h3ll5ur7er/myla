#!/usr/bin/env bash
# build.sh <source.my> [out]: compile with the self-hosted compiler (run
# scripts/bootstrap.sh first). Works from any directory.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
input="$1"
out="${2:-a.out}"
obj="$(mktemp --suffix=.o)"

trap 'rm -f "$obj"' EXIT

"$repo/build/stage3" "$input" "$repo/lib" | as --64 -o "$obj" -
ld -o "$out" "$obj"
