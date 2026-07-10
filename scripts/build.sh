#!/usr/bin/env bash
set -euo pipefail

input="$1"
out="${2:-a.out}"
obj="$(mktemp --suffix=.o)"

trap 'rm -f "$obj"' EXIT

./build/stage3 "$input" | as --64 -o "$obj" -
ld -o "$out" "$obj"