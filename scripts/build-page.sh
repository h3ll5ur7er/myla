#!/usr/bin/env bash
#
# build-page.sh — the playground page (MYLA-158): tools/wasm/page.html, the
# page API and WASI shim it loads, and play.wasm (selfhost/play_main.my built
# for wasm32-wasi), in one directory any static server can serve.
#
# Usage: scripts/build-page.sh [OUT_DIR]   (default build/page; MYLA names the
# compiler, default build/myla from scripts/bootstrap.sh)

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
OUT_DIR="${1:-build/page}"
MYLA="${MYLA:-build/myla}"
mkdir -p "$OUT_DIR"
# (the toolchain's own warnings shown only when the build fails)
if ! "$MYLA" build selfhost/play_main.my --target wasm32-wasi -o "$OUT_DIR/play.wasm" 2> "$OUT_DIR/build.log"; then
    cat "$OUT_DIR/build.log" >&2
    exit 1
fi
rm -f "$OUT_DIR/build.log"
cp tools/wasm/page.html tools/wasm/myla.mjs tools/wasm/wasi.mjs tools/wasm/mem_fs.mjs "$OUT_DIR/"
echo "page: $OUT_DIR (serve it, then open page.html)"
