#!/usr/bin/env bash
#
# bootstrap.sh — build the self-hosted Myla compiler and verify the
# three-stage fixpoint (the definition of "self-hosted", per docs/Project/Roadmap.md).
#
#   stage0: the seed (bootstrap/seed.s, the compiler's own assembly, D101) is
#           assembled and linked                                  -> stage0
#   stage1: stage0 compiles the Myla-written compiler            -> gen_tool
#   stage2: gen_tool compiles the compiler                         -> stage2(.s)
#   stage3: stage2 compiles the compiler                           -> stage3(.s)
#   check : assert stage2.s == stage3.s  (byte-identical fixed point)
#   cli   : stage3 compiles the `myla` command-line tool          -> myla
#
# A seed older than the sources is an older compiler: stage1 is the current
# compiler built by it, and stage2 the first one the current compiler built,
# so stage2.s and stage3.s are both the current compiler's output.
#
# Usage:
#   scripts/bootstrap.sh [OUT_DIR]
#
# OUT_DIR defaults to ./build (gitignored). Until MYLA-219 the Python toolchain
# could build stage1 instead (the branch backup/python-toolchain-final).
#
# Requires: GNU as + ld (no third-party deps, no libc — decisions D1/D2).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

OUT_DIR="${1:-build}"
SEED="bootstrap/seed.s"
ENTRY="selfhost/gen_main.my"   # amalgamating front end + codegen entry point
STDLIB_ROOT="lib"              # where the bundled `std/` package lives

mkdir -p "$OUT_DIR"

# Assemble + link a generated .s into a static, libc-free ELF executable.
asm_to_bin() {  # <src.s> <out-bin>
    as --64 -o "${2}.o" "$1"
    ld -o "$2" "${2}.o"
}

if [ ! -f "$SEED" ]; then
    echo "FAIL: no $SEED (it is committed; restore it from Git)" >&2
    exit 1
fi
echo "==> stage0: the seed ($SEED), assembled and linked"
asm_to_bin "$SEED" "$OUT_DIR/stage0"
echo "==> stage1: stage0 compiles the self-hosted compiler (gen_tool)"
"$OUT_DIR/stage0" "$ENTRY" "$STDLIB_ROOT" > "$OUT_DIR/gen_tool.s"
asm_to_bin "$OUT_DIR/gen_tool.s" "$OUT_DIR/gen_tool"

echo "==> stage2: gen_tool compiles the compiler"
"$OUT_DIR/gen_tool" "$ENTRY" "$STDLIB_ROOT" > "$OUT_DIR/stage2.s"
asm_to_bin "$OUT_DIR/stage2.s" "$OUT_DIR/stage2"

echo "==> stage3: stage2 compiles the compiler"
"$OUT_DIR/stage2" "$ENTRY" "$STDLIB_ROOT" > "$OUT_DIR/stage3.s"
asm_to_bin "$OUT_DIR/stage3.s" "$OUT_DIR/stage3"

echo "==> fixpoint: comparing stage2.s and stage3.s"
if cmp -s "$OUT_DIR/stage2.s" "$OUT_DIR/stage3.s"; then
    bytes="$(wc -c < "$OUT_DIR/stage2.s")"
    echo "OK: byte-identical fixpoint reached (${bytes} bytes)"
    echo "Self-hosted compiler: $OUT_DIR/stage3"
else
    echo "FAIL: stage2.s and stage3.s differ" >&2
    diff "$OUT_DIR/stage2.s" "$OUT_DIR/stage3.s" | head -40 >&2
    exit 1
fi

echo "==> cli: stage3 builds the myla command-line tool"
"$OUT_DIR/stage3" selfhost/main.my "$STDLIB_ROOT" > "$OUT_DIR/myla.s"
asm_to_bin "$OUT_DIR/myla.s" "$OUT_DIR/myla"
echo "Self-hosted CLI: $OUT_DIR/myla (run / test / build)"

echo "==> cli: it reports a type error with exit status 1"
# (MYLA-80: `build` crashed here, as only the self-compiled CLI handles `?` in
# its own code generator, which no other test runs)
err_file=examples/errors/type_str_index_assign.my
for cmd in build run; do
    set +e
    if [ "$cmd" = build ]; then
        "$OUT_DIR/myla" build "$err_file" -o "$OUT_DIR/err_out" > /dev/null 2> "$OUT_DIR/err.txt"
    else
        "$OUT_DIR/myla" run "$err_file" > /dev/null 2> "$OUT_DIR/err.txt"
    fi
    code=$?
    set -e
    if [ "$code" != 1 ] || ! grep -q "^type error:" "$OUT_DIR/err.txt"; then
        echo "FAIL: myla $cmd on a type error exited with $code" >&2
        cat "$OUT_DIR/err.txt" >&2
        exit 1
    fi
done
echo "OK: build and run report it and exit with 1"

echo "==> lsp: stage3 builds the language server (MYLA-80)"
"$OUT_DIR/stage3" tools/lsp/main.my "$STDLIB_ROOT" > "$OUT_DIR/myla-lsp.s"
asm_to_bin "$OUT_DIR/myla-lsp.s" "$OUT_DIR/myla-lsp"
frame() { printf 'Content-Length: %d\r\n\r\n%s' "${#1}" "$1"; }
reply="$({ frame '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"capabilities":{}}}'
           frame '{"jsonrpc":"2.0","id":2,"method":"shutdown"}'
           frame '{"jsonrpc":"2.0","method":"exit"}'; } | "$OUT_DIR/myla-lsp")"
if ! printf '%s' "$reply" | grep -q '"id":2,"result":null'; then
    echo "FAIL: the language server did not answer initialize and shutdown" >&2
    printf '%s\n' "$reply" >&2
    exit 1
fi
echo "Language server: $OUT_DIR/myla-lsp"
