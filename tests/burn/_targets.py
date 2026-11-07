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
    "tests.burn.test_platform_primitives",
    "tests.burn.test_unit_type",
    "tests.burn.test_defer",
    "tests.burn.test_format_specs",
    "tests.burn.test_slices",
    "tests.burn.test_builtin_impls",
    "tests.burn.test_default_params",
    "tests.burn.test_let_else",
    "tests.burn.test_ir_contract",
    "tests.burn.test_map_remove",
]

# A test that reads the x86-64 code ends there, skipped, on another target,
# after its program ran (`_x86_only` in test_selfhost_codegen); one that only
# reads it is listed here.
_X86_CODE = "it reads the x86-64 assembly"
_X86_TESTS = [
    "test_selfhost_codegen.SelfHostedCodegenParity.test_derived_eq_on_a_plain_enum_compares_tags",
]

_BOTH = {
    **{t: _X86_CODE for t in _X86_TESTS},
}

SKIP: dict[str, dict[str, str]] = {
    "aarch64-linux": _BOTH,
    "wasm32-wasi": {
        **_BOTH,
        "test_selfhost_codegen.SelfHostedCodegenParity.test_children_run_in_parallel": "one worker (D125 (4))",
        # the linear memory (run.mjs's MYLA_WASM_MEMORY_OUT, MYLA-297) counts
        # each 16 MiB chunk whole once used, and the 8 MiB shadow stack: 80 MB
        # for this program, whose native peak RSS (touched pages) is 18 MB
        "test_selfhost_codegen.SelfHostedCodegenParity.test_deep_task_trees_and_awaits":
            "a chunk counts whole in the linear memory (80 MB; 18 MB of pages touched natively)",
        # no processes (D125, Language/Targets): `run` and `spawn` are
        # `Unsupported` there, which test_wasm checks
        "test_process": "WASI has no processes (test_wasm checks they are Unsupported)",
        "test_stdio.BrokenPipe.test_a_write_to_another_descriptor_reports_it":
            "a WASI program has the descriptors 0 to 2 only (and its preopened directories)",
        # MYLA-336's children with pipes: `Unsupported` there, which
        # PipesOnWasm checks; and WASI has no permission bits
        "test_platform_primitives.Pipes": "WASI has no processes (PipesOnWasm checks they are Unsupported)",
        "test_platform_primitives.Descriptors.test_the_mode_given": "WASI has no permission bits",
    },
}

# Programs inside a test's loop a target is excused from.
SKIP_PROGRAMS: dict[str, dict[str, str]] = {
    "wasm32-wasi": {
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
