#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <directory>"
  exit 1
fi

dir="$1"

if [[ ! -d "$dir" ]]; then
  echo "Error: directory not found: $dir"
  exit 1
fi

shopt -s nullglob

files=("$dir"/*.my)

if [[ ${#files[@]} -eq 0 ]]; then
  echo "No .my files found in: $dir"
  exit 0
fi

mkdir -p ./build

for source_file in "${files[@]}"; do
  base_name="$(basename "$source_file")"
  exe_name="${base_name%.*}"
  exe_path="./build/$exe_name"

  echo "==> Building $source_file"
  ./scripts/build.sh "$source_file" "$exe_path"

  echo "==> Running $exe_path"
  "$exe_path"

  echo
done