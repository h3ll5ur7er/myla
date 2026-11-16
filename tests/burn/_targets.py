"""Which burn suites run on which target, and what each target is excused from,
with why (MYLA-268, Language/Targets). `scripts/test-target.py <target>` runs
SUITES with MYLA_TEST_TARGET set: the native helpers (`_native.py`) then build
for the target and run under qemu-aarch64, Node or Wine, and the tests below are
skipped with their reason. A program inside a test's loop that a target is
excused from is skipped by the loop itself (`program_excuse`)."""
from __future__ import annotations

import os

TARGETS = ["aarch64-linux", "wasm32-wasi", "x86_64-windows"]

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
    # every platform module the same interface, in Myla's terms (MYLA-701)
    "tests.burn.test_platform_interface",
    "tests.burn.test_net",
    "tests.burn.test_term",
    "tests.burn.test_http",
    # a deadline's end and a cancel beside many timers (MYLA-456)
    "tests.burn.test_timer_scaling",
    # a wait for a descriptor beside many others, one frame woken per
    # readiness (MYLA-518)
    "tests.burn.test_reactor_scaling",
    "tests.burn.test_unit_type",
    "tests.burn.test_defer",
    "tests.burn.test_format_specs",
    "tests.burn.test_slices",
    "tests.burn.test_builtin_impls",
    "tests.burn.test_default_params",
    "tests.burn.test_let_else",
    "tests.burn.test_operator_traits",
    "tests.burn.test_float_methods",
    "tests.burn.test_float_keys",
    "tests.burn.test_linalg",
    "tests.burn.test_ir_contract",
    # integer overflow, checked and plain (D175)
    "tests.burn.test_overflow",
    "tests.burn.test_map_remove",
    # every standard library module's cases through the harness (MYLA-370:
    # on wasm32 too, every case run)
    "tests.burn.test_std_modules",
    # std.toml against tomllib and the toml-test suite, its drivers built for
    # the target (MYLA-424)
    "tests.burn.test_toml",
    # the review's generators: deep copies between tasks, reads beside a
    # mutation, writes into containers, generic code per width, the
    # library at extreme arguments, the parsers built --checked (MYLA-555)
    "tests.burn.test_generated_deep_copies",
    "tests.burn.test_generated_reads",
    "tests.burn.test_generated_writes",
    "tests.burn.test_generated_widths",
    "tests.burn.test_generated_extremes",
    "tests.burn.test_formats_checked",
    # std.http's router (D202): last, so the suites before it keep the
    # schedule they had without it (the timing tests among them, test_http's
    # and test_stdio's, run beside the same neighbours)
    "tests.burn.test_router",
]

# A test that reads the x86-64 code ends there, skipped, on another target,
# after its program ran (`_x86_only` in test_selfhost_codegen); one that only
# reads it is listed here.
_X86_CODE = "it reads the x86-64 assembly"
_X86_TESTS = [
    "test_selfhost_codegen.SelfHostedCodegenParity.test_derived_eq_on_a_plain_enum_compares_tags",
]

_WINE_LINKS = "Wine shows a Unix symbolic link as what it names, not as a link (a reparse point)"
_WIN_LINUX_TOOLS = "it runs Linux's tools, which a Windows program can't (test_process.WindowsChildren runs Windows' own)"
# MYLA-707: Windows' console has no termios and its programs no Unix signals
_WIN_TERMIOS = ("it reads the terminal's termios, which Wine's console sets itself, and sends Unix signals: "
                "test_windows.Console checks the console's mode through a program sharing it")
_WIN_SIGNALS = ("a Unix signal is Wine's (SIGINT a Ctrl-C, the rest end Wine), and Windows' default for a Ctrl-C "
                "is an exit code (Wine's 0): test_windows.Console sends Ctrl-C, MYLA-708's runner the close")

_BOTH = {
    **{t: _X86_CODE for t in _X86_TESTS},
    "test_std_modules.StdModuleCases.test_interpreted": "the interpreter's runs are the host's",
}

SKIP: dict[str, dict[str, str]] = {
    "aarch64-linux": {
        **_BOTH,
        # a qemu-aarch64 process per case: std.int's 1826 take too long
        "test_std_modules.StdModuleCases.test_native": "a qemu process per case (std.int's 1826 cases take too long)",
    },
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
        # MYLA-346: WASI preview 1 has no sockets, which NetOnWasm checks are
        # `Unsupported`; the addresses, the hosts file and the warnings run
        **{f"test_net.{c}": "WASI has no sockets (NetOnWasm checks they are Unsupported)"
           for c in ["Tcp", "Udp", "Dns", "Errors", "Primitives"]},
        **{f"test_reactor_scaling.{c}": "WASI has no sockets (its Readers run)"
           for c in ["RoundTrips", "Accepts", "Closed", "Lots"]},
        # MYLA-350: WASI preview 1 has no terminal modes and no signals, which
        # TermOnWasm checks are `Unsupported` (nothing a terminal, no size)
        **{f"test_term.{c}": "WASI has no terminals or signals (TermOnWasm checks they are Unsupported)"
           for c in ["Terminal", "Signals", "Primitives", "RawModeEnds"]},
    },
    # MYLA-702: Windows' first step has the standard streams, the heap, the
    # clocks, the arguments and the environment, and tasks (on as many
    # workers as on Linux since MYLA-703); files, directories and paths
    # (MYLA-704); child processes (MYLA-705); what its later steps bring is
    # `Unsupported` until then (D210), which NetOnWasm, TermOnWasm and
    # HttpOnWasm check there too
    "x86_64-windows": {
        **_BOTH,
        "test_stdio.BrokenPipe.test_a_write_to_another_descriptor_reports_it":
            "a Windows descriptor is a handle: Wine hands a program no Unix descriptor 3",
        "test_platform_primitives.Descriptors.test_the_mode_given":
            "Windows has no permission bits but the read-only attribute (D218): the mode given isn't used",
        # MYLA-704: Windows' links are reparse points, which Wine doesn't
        # make of a Unix link: it shows one as what it names (MYLA-708 runs
        # these on Windows)
        **{t: _WINE_LINKS for t in ["test_platform_primitives.Paths",
                                    "test_fs.DirectoryParity.test_symbolic_links"]},
        "test_fs.DirectoryParity.test_current_dir_removed":
            "Windows can't remove a working directory, and Wine starts a program whose one is gone in C:\\windows",
        # MYLA-705: Windows' children are Windows programs; Linux's tools
        # (/bin/sh, echo, cat) aren't on its PATH, and Wine starts one
        # without its standard handles or its exit code
        **{t: _WIN_LINUX_TOOLS for t in [
            "test_process.TestSubprocessExample",
            "test_process.TestSubprocessParity.test_captures_stdout",
            "test_process.TestSubprocessParity.test_captures_stderr_and_exit_code",
            "test_process.TestSubprocessParity.test_command_builder_matches_run",
            "test_process.TestSubprocessParity.test_a_child_s_path_directory_environment_and_input",
            "test_process.TestSubprocessParity.test_an_environment_name_no_variable_can_have",
            "test_process.TestSubprocessParity.test_a_child_waited_for_in_a_task",
            "test_platform_primitives.Pipes",
        ]},
        "test_process.TestSubprocessParity.test_reports_terminating_signal":
            "Windows has no signals: `kill` ends a child with the exit code 1 (WindowsChildren checks it)",
        "test_process.TestSubprocessParity.test_a_child_gets_sigpipe_back": "Windows has no SIGPIPE",
        **{f"test_net.{c}": "Windows' sockets come with MYLA-706 (NetOnWasm checks they are Unsupported)"
           for c in ["Tcp", "Udp", "Dns", "Errors", "Primitives"]},
        **{f"test_reactor_scaling.{c}": "Windows' sockets come with MYLA-706 (its Readers run)"
           for c in ["RoundTrips", "Accepts", "Closed", "Lots"]},
        "test_router.Router": "Windows' sockets come with MYLA-706",
        # MYLA-707: the console and Ctrl-C under Wine, which
        # test_windows.Console checks; what rests on Unix's signals and
        # termios is Linux's
        "test_term.RawModeEnds": _WIN_TERMIOS,
        "test_term.Terminal.test_raw_mode_and_back":
            "Wine's console has no virtual-terminal input (an arrow is dropped, Ctrl-C ends a read): "
            "test_windows.Console reads plain keys, MYLA-708's runner the rest",
        **{f"test_term.Signals.{t}": _WIN_SIGNALS
           for t in ["test_awaited_while_another_task_runs", "test_interrupted_without_tasks",
                     "test_a_program_that_never_listens_ends", "test_a_sent_sigsegv_ends_the_program",
                     "test_an_ignored_signal_stays_ignored"]},
        # the start makes the command line and the environment UTF-8 in
        # the heap, so a cell freed then is taken again before a new one
        "test_selfhost_codegen.SelfHostedCodegenParity.test_a_runtime_variable_is_its_own_operand":
            "Windows' start allocates (the arguments made UTF-8), so the heap isn't fresh at `main`",
        **{t: "Wine gives a program its Windows path as argv[0] (`Z:\\…\\prog`), not the argv0 asked for"
           for t in ["test_stdio.TestArgsExample.test_native_matches_interpreter",
                     "test_stdio.TestStdioParity.test_args_round_trip"]},
    },
}

# Programs inside a test's loop a target is excused from (and std's modules
# in test_std_modules, as `std.<name>`).
SKIP_PROGRAMS: dict[str, dict[str, str]] = {
    "wasm32-wasi": {
        "io_through_the_ir": "it runs a child process, which WASI has none of",
    },
    "x86_64-windows": {
        "io_through_the_ir": "it runs Linux's /bin/echo, which a Windows program can't (MYLA-705)",
        # its children are cat, sh and head (MYLA-705)
        "std.process": _WIN_LINUX_TOOLS,
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
