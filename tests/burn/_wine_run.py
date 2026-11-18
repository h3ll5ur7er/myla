"""Runs a Windows program under Wine so that its output ends when the program
does (MYLA-759): `python3 -I -S _wine_run.py WINE... PROGRAM ARGS...`.

The first program of a Wine server starts the prefix's services (services.exe,
winedevice.exe, plugplay.exe, svchost.exe, rpcss.exe), which outlive it holding
its standard error, in sessions of their own, for as long as the server lives:
a test reading the program's output through pipes waited for them, not for
the program. On master's e6e1b9e a run of `scopes_wait_for_children` ended
in a second and its `subprocess.run` timed out at 60 s, and on 4c91ba2 a run
without a time limit waited past the job's 75 minutes, while other suites'
programs kept the server alive.

So this process becomes Wine, the program (`exec`: its caller's pid, signals
and time limits are the program's), with its standard output and error pipes
of a copier's: a child that copies them to the caller's as they come, and
once the program has ended (the copier's parent changed), copies what they
still hold and ends, whoever still holds them. Standard input is the
program's own.
"""
import os
import select
import sys

CHUNK = 65536


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: _wine_run.py WINE... PROGRAM ARGS...", file=sys.stderr)
        return 2
    # (one pipe for both when the caller's are one, so that they keep
    # their order)
    one = os.fstat(1)
    two = os.fstat(2)
    same = (one.st_dev, one.st_ino) == (two.st_dev, two.st_ino)
    pipes = [os.pipe()] if same else [os.pipe(), os.pipe()]
    program = os.getpid()
    if os.fork() == 0:
        copier(program, pipes)
    for fd, (r, w) in zip((1, 2), pipes):
        # (a caller's output that doesn't block, the program's neither)
        blocking = os.get_blocking(fd)
        os.dup2(w, fd)
        os.set_blocking(fd, blocking)
        os.close(r)
        os.close(w)
    if same:
        os.dup2(1, 2)
    os.execvp(argv[0], argv)
    return 127


def copier(program: int, pipes) -> None:
    """The pipes' read ends copied to this process's standard output and
    error until the process `program` has ended, then what they still hold;
    then this process ends."""
    try:
        os.close(0)
        copies = {}
        for fd, (r, w) in zip((1, 2), pipes):
            os.close(w)
            os.set_blocking(r, False)
            copies[r] = fd
        while copies and os.getppid() == program:
            try:
                ready, _, _ = select.select(list(copies), [], [], 0.05)
            except InterruptedError:
                ready = []
            for r in ready:
                if copy(r, copies[r]) == 0:
                    del copies[r]
        # the program has ended (or closed both): what it wrote is in them
        for r, fd in copies.items():
            while copy(r, fd) > 0:
                pass
    finally:
        os._exit(0)


def copy(r: int, fd: int) -> int:
    """What the pipe `r` holds now copied to `fd`: 1, else 0 at its end or
    -1 when it holds nothing now."""
    try:
        data = os.read(r, CHUNK)
    except (BlockingIOError, InterruptedError):
        return -1
    if not data:
        return 0
    view = memoryview(data)
    while view:
        try:
            view = view[os.write(fd, view):]
        except BlockingIOError:
            select.select([], [fd], [], 1)
        except BrokenPipeError:
            break
        except InterruptedError:
            pass
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
