"""A program run under a time limit that, when the limit is hit, leaves what
is needed to see where it hung (MYLA-418; the review of 2026-11-10 saw a
rare hang of an aarch64 stress program under qemu, {R2} §1.6).

`run_watched` is `subprocess.run(…, capture_output=True, timeout=…)`; on the
timeout, before the program is killed, it takes the stacks of its threads
with gdb where gdb can attach (a native program's; qemu's own for a program
it emulates), then sends it SIGQUIT with core dumps allowed, so that the
kernel (a native program) or qemu-user (the guest's, `qemu_<name>_….core`)
writes a core, moved to a directory that is kept: MYLA_HANG_DIR, else
`myla-hangs` in the temporary directory. The `Hung` it raises (a
`TimeoutExpired`) names the directory and carries the stacks, in a test's
failure message."""
from __future__ import annotations

import os
import resource
import shutil
import signal
import subprocess
import tempfile
import time


class Hung(subprocess.TimeoutExpired):
    """A timeout whose message says where its core and stacks are."""

    def __init__(self, cmd, timeout, kept: str, stacks: str, stderr) -> None:
        super().__init__(cmd, timeout, output=None, stderr=stderr)
        self.kept = kept
        self.stacks = stacks

    def __str__(self) -> str:
        return f"{super().__str__()}; cores and stacks kept in {self.kept}\n{self.stacks[-3000:]}"


def _allow_cores() -> None:
    # as large as the hard limit lets (a user can't raise that)
    soft, hard = resource.getrlimit(resource.RLIMIT_CORE)
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (hard, hard))
    except (ValueError, OSError):
        pass


def hang_dir() -> str:
    """Where the cores and stacks of programs that hung are kept."""
    d = os.environ.get("MYLA_HANG_DIR") or os.path.join(tempfile.gettempdir(), "myla-hangs")
    os.makedirs(d, exist_ok=True)
    return d


def _stacks(pid: int) -> str:
    if not shutil.which("gdb"):
        return "(no gdb for the stacks)"
    try:
        g = subprocess.run(["gdb", "-p", str(pid), "-batch", "-ex", "thread apply all bt"],
                           capture_output=True, text=True, timeout=60)
        return g.stdout
    except (subprocess.TimeoutExpired, OSError) as e:
        return f"(gdb failed: {e})"


def run_watched(cmd: list[str], timeout: float, text: bool = True, env: dict | None = None,
                cwd: str | None = None, input: str | bytes | None = None) -> subprocess.CompletedProcess:
    """`cmd` run to its end, its output captured; on `timeout`, its stacks
    and a core kept (`hang_dir`), then `subprocess.TimeoutExpired`."""
    with tempfile.TemporaryDirectory() as scratch:
        # the core is written in the program's directory: a scratch one
        # unless the caller names one, searched for it afterwards
        where = cwd or scratch
        before = set(os.listdir(where))
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text, env=env,
                             cwd=where, preexec_fn=_allow_cores)
        try:
            out, err = p.communicate(input, timeout=timeout)
            return subprocess.CompletedProcess(cmd, p.returncode, out, err)
        except subprocess.TimeoutExpired:
            pass
        stacks = _stacks(p.pid)
        p.send_signal(signal.SIGQUIT)
        try:
            out, err = p.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
            out, err = p.communicate()
        time.sleep(0.5)
        keep = os.path.join(hang_dir(), f"{os.path.basename(cmd[-1])}-{os.getpid()}-{time.time_ns()}")
        os.makedirs(keep)
        for name in set(os.listdir(where)) - before:
            if "core" in name:
                shutil.move(os.path.join(where, name), os.path.join(keep, name))
        with open(os.path.join(keep, "stacks.txt"), "w", encoding="utf-8") as fh:
            fh.write(f"{cmd}\n\n{stacks}")
        raise Hung(cmd, timeout, keep, stacks, err)
