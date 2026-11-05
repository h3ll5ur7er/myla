#!/usr/bin/env bash
#
# install-hooks.sh — turn on the repository's Git hooks (.githooks/) for this
# clone: the pre-push check that the seeds (bootstrap/seed*.s) are the current compiler
# (MYLA-218). `git config --unset core.hooksPath` turns them off again.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
git config core.hooksPath .githooks
echo "hooks on: $(git config core.hooksPath) (pre-push checks the seeds)"
