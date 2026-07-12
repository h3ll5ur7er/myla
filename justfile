default:
    @just --list

bs *args:
    @uv run myla.py {{args}}

asm2bin asm bin:
    as --64 -o {{bin}}.o {{asm}}
    ld -o {{bin}} {{bin}}.o

bootstrap:
    @uv run timer.py start --name bootstrap --file build/bootstrap_timers.json
    @echo "==> stage1: Python toolchain builds the self-hosted compiler (gen_tool)"
    @uv run myla.py build selfhost/gen_main.my -o build/gen_tool
    @uv run timer.py get --name bootstrap --file build/bootstrap_timers.json
    @echo "==> stage2: gen_tool compiles the compiler"
    ./build/gen_tool selfhost/gen_main.my src/myla > build/stage2.s
    just asm2bin build/stage2.s build/stage2
    @uv run timer.py get --name bootstrap --file build/bootstrap_timers.json
    @echo "==> stage3: stage2 compiles the compiler"
    ./build/stage2 selfhost/gen_main.my src/myla > build/stage3.s
    just asm2bin build/stage3.s build/stage3
    @uv run timer.py get --name bootstrap --file build/bootstrap_timers.json
    @echo "==> fixpoint: comparing stage2.s and stage3.s"
    if cmp -s "build/stage2.s" "build/stage3.s"; then \
        bytes="$(wc -c < "build/stage2.s")";\
        echo "OK: byte-identical fixpoint reached (${bytes} bytes)";\
    else \
        echo "FAIL: stage2.s and stage3.s differ" >&2;\
        diff "build/stage2.s" "build/stage3.s" | head -40 >&2;\
        exit 1;\
    fi
    @uv run timer.py get --name bootstrap --file build/bootstrap_timers.json
    @echo "==> stage4: building the myla CLI -> build/myla"
    ./build/stage3 selfhost/main.my src/myla > build/myla.s
    just asm2bin build/myla.s build/myla
    @echo "==> done: build/myla provides run / test / build"
    @uv run timer.py stop --name bootstrap --file build/bootstrap_timers.json

build source output:
	#!/usr/bin/env bash
	set -euo pipefail

	mkdir -p "$(dirname "{{output}}")"

	# The self-hosted `myla` CLI type-checks, generates assembly, and drives
	# `as`/`ld` itself (via subprocess) to produce the binary.
	./build/myla build "{{source}}" -o "{{output}}"


run source *args:
	./build/myla run "{{source}}"

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