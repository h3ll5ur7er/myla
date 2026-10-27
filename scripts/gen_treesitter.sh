#!/usr/bin/env bash
# gen_treesitter.sh: regenerate editor/tree-sitter-myla from grammar/myla.ebnf
# (MYLA-77). Builds the grammar tool (tools/grammar), writes grammar.js and
# queries/highlights.scm, then runs `tree-sitter generate` for src/ when the
# tree-sitter CLI is available (TREE_SITTER, the package's node_modules, or
# PATH).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

py="${PYTHON:-python3}"
mkdir -p build
$py myla.py build tools/grammar/main.my -o build/grammar >/dev/null
build/grammar treesitter grammar/myla.ebnf tools/grammar/highlights.scm editor/tree-sitter-myla
echo "wrote editor/tree-sitter-myla/grammar.js and queries/highlights.scm"

ts="${TREE_SITTER:-}"
if [ -z "$ts" ] && [ -x editor/tree-sitter-myla/node_modules/.bin/tree-sitter ]; then
    ts="$PWD/editor/tree-sitter-myla/node_modules/.bin/tree-sitter"
fi
if [ -z "$ts" ]; then ts="$(command -v tree-sitter || true)"; fi
if [ -z "$ts" ]; then
    echo "tree-sitter CLI not found: run 'npm install' in editor/tree-sitter-myla, then this again" >&2
    exit 1
fi
(cd editor/tree-sitter-myla && "$ts" generate --abi 14)
echo "regenerated editor/tree-sitter-myla/src"
