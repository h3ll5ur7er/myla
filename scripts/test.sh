#!/usr/bin/env bash
# test.sh [fast|all] — run the test suites (MYLA-58).
#
#   fast  unit and integration tests, and the burn tests that take less than
#         about 4 seconds each (about 20 seconds once the tools are cached)
#   all   every suite (the default; the burn suite takes some 5 minutes)
#
# Uses only the standard library's unittest (pytest works too: uv run pytest). The self-hosted tools the burn
# tests need are built once and cached in build/test-tools/.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

mode="${1:-all}"
py="${PYTHON:-python3}"

$py -m unittest discover -s tests/unit -t .
$py -m unittest discover -s tests/integration -t .
case "$mode" in
    all)
        $py -m unittest discover -s tests/burn -t .
        ;;
    fast)
        # tests/burn without the self-hosting gates (selfhost_*) and the
        # modules that take 4 seconds or more, measured one by one with the
        # tools cached (MYLA-153, 2026-11-01): the broad corpora and the
        # native parity suites; `all` runs them
        slow=(test_compiler_parity test_concurrency_stress test_json test_lsp test_vscode_debugger
              test_native_runtime test_grammar test_fs test_stdin test_declaration_recovery test_toml)
        modules=()
        for f in tests/burn/test_*.py; do
            name="$(basename "$f" .py)"
            [[ "$name" == test_selfhost_* ]] && continue
            [[ " ${slow[*]} " == *" $name "* ]] && continue
            modules+=("tests.burn.$name")
        done
        $py -m unittest "${modules[@]}"
        ;;
    *)
        echo "usage: $0 [fast|all]" >&2
        exit 2
        ;;
esac
