"""Which burn suites run on which target, and what each target is excused from,
with why (MYLA-268, Language/Targets). `scripts/test-target.py <target>` runs
SUITES with MYLA_TEST_TARGET set: the native helpers (`_native.py`) then build
for the target and run under qemu-aarch64 or Node, and the tests below are
skipped with their reason. A program inside a test's loop that a target is
excused from is skipped by the loop itself (`program_excuse`)."""
from __future__ import annotations

import os

TARGETS = ["aarch64-linux", "wasm32-wasi"]

# The suites every target runs: the parity programs, the runtime errors, the
# error corpus's runtime cases, the I/O suites and the language features.
SUITES = [
    "tests.burn.test_selfhost_codegen",
    "tests.burn.test_compiler_parity",
    "tests.burn.test_error_corpus",
    "tests.burn.test_examples_compile",
    "tests.burn.test_modules",
    "tests.burn.test_fs",
    "tests.burn.test_stdio",
    "tests.burn.test_process",
    "tests.burn.test_unit_type",
    "tests.burn.test_defer",
    "tests.burn.test_format_specs",
    "tests.burn.test_slices",
    "tests.burn.test_builtin_impls",
    "tests.burn.test_default_params",
    "tests.burn.test_let_else",
]

# A test that reads the x86-64 code ends there, skipped, on another target,
# after its program ran (`_x86_only` in test_selfhost_codegen); one that only
# reads it is listed here.
_X86_CODE = "it reads the x86-64 assembly"
_X86_TESTS = [
    "test_selfhost_codegen.SelfHostedCodegenParity.test_derived_eq_on_a_plain_enum_compares_tags",
]

# A call in tail position jumps on x86-64 only (MYLA-126, an optimisation:
# D87 guarantees `become`, which every target keeps); these programs recurse
# millions deep through plain calls (MYLA-283).
_PLAIN_TAIL_CALLS = "a plain call in tail position takes a frame here (MYLA-283)"
_TAIL_TESTS = [
    "test_selfhost_codegen.SelfHostedCodegenParity.test_calls_in_tail_position_reuse_the_frame",
    "test_selfhost_codegen.SelfHostedCodegenParity.test_tail_calls_hand_over_owned_arguments",
]

# A function value of a function taking a struct, tuple or enum by copy (a
# `become` hands it over, D88): the x86-64 backend's adapter copies its words;
# aarch64's and wasm32's don't yet (MYLA-282).
_BYVAL_FNVAL = "a function value of a function taking a value by copy isn't built yet (MYLA-282)"

_BOTH = {
    **{t: _X86_CODE for t in _X86_TESTS},
    **{t: _PLAIN_TAIL_CALLS for t in _TAIL_TESTS},
    "test_selfhost_codegen.SelfHostedCodegenParity.test_become_passes_aggregates_by_value": _BYVAL_FNVAL,
    # generated per parity program (test_compiler_parity._make)
    "test_compiler_parity.TestCompilerParity.test_become_passes_aggregates_by_value": _BYVAL_FNVAL,
}

SKIP: dict[str, dict[str, str]] = {
    "aarch64-linux": _BOTH,
    "wasm32-wasi": {
        **_BOTH,
        "test_selfhost_codegen.SelfHostedCodegenParity.test_children_run_in_parallel": "one worker (D125 (4))",
        "test_selfhost_codegen.SelfHostedCodegenParity.test_stress_programs_reclaim_memory":
            "the peak measured is Node's, not the program's",
        "test_selfhost_codegen.SelfHostedCodegenParity.test_deep_task_trees_and_awaits":
            "the peak measured is Node's, not the program's",
        # no processes (D125, Language/Targets): `run` and `spawn` are
        # `Unsupported` there, which test_wasm checks
        "test_process": "WASI has no processes (test_wasm checks they are Unsupported)",
        # the file system WASI shows (MYLA-281): reading a directory gives
        # `Other` for `IsADirectory`, a path's kind differs in the tour, and a
        # removed working directory stops Node's shim
        "test_fs.TestReadFileExample.test_a_directory": "reading a directory is Other, not IsADirectory (MYLA-281)",
        "test_fs.TestWriteToFileParity.test_directory_read_is_a_directory":
            "reading a directory is Other, not IsADirectory (MYLA-281)",
        "test_fs.DirectoryParity.test_tour": "a path's kind differs under WASI (MYLA-281)",
        "test_fs.DirectoryParity.test_current_dir_removed": "a removed working directory stops Node's shim (MYLA-281)",
    },
}

# Programs inside a test's loop a target is excused from.
SKIP_PROGRAMS: dict[str, dict[str, str]] = {
    "aarch64-linux": {"become_passes_aggregates_by_value": _BYVAL_FNVAL},
    "wasm32-wasi": {
        "become_passes_aggregates_by_value": _BYVAL_FNVAL,
        "io_through_the_ir": "it runs a child process, which WASI has none of",
    },
}


def target() -> str:
    return os.environ.get("MYLA_TEST_TARGET", "")


def excuse_for(test_id: str) -> str | None:
    """Why the running target skips the test `test_id` (`module.Class.method`,
    a prefix of it naming a class or module), or None."""
    for key, why in SKIP.get(target(), {}).items():
        short = test_id.removeprefix("tests.burn.")
        if short == key or short.startswith(key + "."):
            return why
    return None


def program_excuse(name: str) -> str | None:
    """Why the running target skips the program `name` of a test's loop."""
    return SKIP_PROGRAMS.get(target(), {}).get(name)
