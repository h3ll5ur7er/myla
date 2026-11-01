default:
    @just --list

# The Python toolchain (no dependencies beyond Python's standard library).
bs *args:
    @python3 myla.py {{args}}

# Build the self-hosted compiler (checking the fixed point) and the myla CLI.
bootstrap:
    scripts/bootstrap.sh

build source output:
	#!/usr/bin/env bash
	set -euo pipefail

	mkdir -p "$(dirname "{{output}}")"

	# The self-hosted `myla` CLI type-checks, generates assembly, and drives
	# `as`/`ld` itself (via subprocess) to produce the binary.
	./build/myla build "{{source}}" -o "{{output}}"


run source *args:
	./build/myla run "{{source}}" {{args}}

test source:
	./build/myla test "{{source}}"

run-all dir:
	#!/usr/bin/env bash
	set -euo pipefail

	dir="{{dir}}"

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

	for source_file in "${files[@]}"; do
	  base_name="$(basename "$source_file")"
	  exe_name="${base_name%.*}"
	  exe_path="./build/$exe_name"

	  echo "==> Building $source_file"
	  just build "$source_file" "$exe_path"

	  echo "==> Running $exe_path"
	  "$exe_path"

	  echo
	done