#!/usr/bin/env bash
# test.sh [fast|all] — run the test suites (MYLA-58).
#
#   fast  unit and integration tests, and the burn tests without the
#         self-hosting gates (about 20 seconds once the tools are cached)
#   all   every suite, the self-hosting gates included (the default)
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
        # everything in tests/burn except the self-hosting gates (selfhost_*)
        modules=()
        for f in tests/burn/test_*.py; do
            name="$(basename "$f" .py)"
            [[ "$name" == test_selfhost_* ]] && continue
            modules+=("tests.burn.$name")
        done
        $py -m unittest "${modules[@]}"
        ;;
    *)
        echo "usage: $0 [fast|all]" >&2
        exit 2
        ;;
esac
