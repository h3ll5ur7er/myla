#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <source.my> [program args...]"
  exit 1
fi

source_file="$1"
shift

if [[ ! -f "$source_file" ]]; then
  echo "Error: source file not found: $source_file"
  exit 1
fi

mkdir -p ./build

base_name="$(basename "$source_file")"
exe_name="${base_name%.*}"
exe_path="./build/$exe_name"

./scripts/build.sh "$source_file" "$exe_path"

"$exe_path" "$@"
