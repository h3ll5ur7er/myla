#!/usr/bin/env bash
#
# bootstrap.sh — build the self-hosted Myla compiler and verify the
# three-stage fixpoint (the definition of "self-hosted", per docs/Project/Roadmap.md).
#
#   stage1: the Python toolchain compiles the Myla-written compiler -> gen_tool
#   stage2: gen_tool compiles the compiler                         -> stage2(.s)
#   stage3: stage2 compiles the compiler                           -> stage3(.s)
#   check : assert stage2.s == stage3.s  (byte-identical fixed point)
#   cli   : stage3 compiles the `myla` command-line tool          -> myla
#
# Usage:
#   scripts/bootstrap.sh [OUT_DIR]
#
# OUT_DIR defaults to ./build (gitignored). Override the Python entry point with
# the MYLA env var (default: "python3 myla.py").
#
# Requires: python3, GNU as + ld (no third-party deps, no libc — decisions D1/D2).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

OUT_DIR="${1:-build}"
ENTRY="selfhost/gen_main.my"   # amalgamating front end + codegen entry point
STDLIB_ROOT="src/myla"         # where the bundled `std/` package lives
MYLA="${MYLA:-python3 myla.py}"

mkdir -p "$OUT_DIR"

# Assemble + link a generated .s into a static, libc-free ELF executable.
asm_to_bin() {  # <src.s> <out-bin>
    as --64 -o "${2}.o" "$1"
    ld -o "$2" "${2}.o"
}

echo "==> stage1: Python toolchain builds the self-hosted compiler (gen_tool)"
$MYLA build "$ENTRY" -o "$OUT_DIR/gen_tool"

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
