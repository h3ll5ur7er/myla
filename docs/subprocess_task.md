The overall design is:

1. Create one pipe for stdout.
2. Create another pipe for stderr.
3. Create a child process with `fork`.
4. In the child:

   * Redirect pipe write ends onto file descriptors 1 and 2.
   * Close unused descriptors.
   * Replace the process with the requested executable using `execve`.
5. In the parent:

   * Close the pipe write ends.
   * Read both pipes concurrently.
   * Call `wait4` to collect the child’s termination status.
   * Decode the exit code or terminating signal.

`fork()` duplicates the current process, while `execve()` replaces the child process image with another executable. ([man7.org][1])

## 1. Raw syscall convention

On Linux x86-64:

```text
rax = syscall number
rdi = argument 1
rsi = argument 2
rdx = argument 3
r10 = argument 4
r8  = argument 5
r9  = argument 6

syscall

rax = result
```

`syscall` destroys `rcx` and `r11`.

A syscall failure is normally returned as a negative integer in the range `-4095..-1`, representing `-errno`.

A useful check is:

```asm
syscall
cmp rax, -4095
jae .error
```

## 2. Relevant syscall numbers

For the native Linux x86-64 ABI:

```asm
SYS_read       equ 0
SYS_write      equ 1
SYS_close      equ 3
SYS_poll       equ 7
SYS_pipe       equ 22
SYS_dup2       equ 33
SYS_fork       equ 57
SYS_execve     equ 59
SYS_exit       equ 60
SYS_wait4      equ 61

SYS_dup3       equ 292
SYS_pipe2      equ 293
```

Using `pipe2(..., O_CLOEXEC)` and `dup3` is usually cleaner, but plain `pipe` and `dup2` are sufficient for a first implementation.

## 3. Pipe representation

A pipe gives you two file descriptors:

```text
pipefd[0] = read end
pipefd[1] = write end
```

Allocate space for two 32-bit integers:

```asm
section .bss
stdout_pipe: resd 2
stderr_pipe: resd 2
child_status: resd 1
```

Create the pipes:

```asm
mov eax, SYS_pipe
lea rdi, [rel stdout_pipe]
syscall
test rax, rax
js .error

mov eax, SYS_pipe
lea rdi, [rel stderr_pipe]
syscall
test rax, rax
js .error
```

On x86-64, file descriptors are integers, so access them with 32-bit loads:

```asm
mov edi, dword [rel stdout_pipe + 0] ; read end
mov edi, dword [rel stdout_pipe + 4] ; write end
```

## 4. Forking

```asm
mov eax, SYS_fork
syscall

test rax, rax
js .fork_error
jz .child

; Parent:
mov r12, rax                 ; child PID
jmp .parent
```

The return value differs by process:

```text
rax < 0     error
rax = 0     executing in child
rax > 0     executing in parent; value is child PID
```

## 5. Child setup

The child must make:

```text
fd 1 -> stdout pipe write end
fd 2 -> stderr pipe write end
```

With `dup2`:

```asm
.child:
    ; dup2(stdout_pipe[1], STDOUT_FILENO)
    mov eax, SYS_dup2
    mov edi, dword [rel stdout_pipe + 4]
    mov esi, 1
    syscall
    test rax, rax
    js .child_failure

    ; dup2(stderr_pipe[1], STDERR_FILENO)
    mov eax, SYS_dup2
    mov edi, dword [rel stderr_pipe + 4]
    mov esi, 2
    syscall
    test rax, rax
    js .child_failure
```

Now close all four original pipe descriptors:

```asm
    mov edi, dword [rel stdout_pipe + 0]
    call close_fd

    mov edi, dword [rel stdout_pipe + 4]
    call close_fd

    mov edi, dword [rel stderr_pipe + 0]
    call close_fd

    mov edi, dword [rel stderr_pipe + 4]
    call close_fd
```

Closing the original write descriptors is important. After `dup2`, descriptors 1 and 2 refer to the same underlying pipe endpoints, so the originals are unnecessary.

A simple internal syscall helper might be:

```asm
close_fd:
    mov eax, SYS_close
    syscall
    ret
```

In production code, be careful that your helper’s calling convention matches your language’s generated calling convention.

## 6. Building `argv` and `envp`

`execve` has this interface:

```text
execve(path, argv, envp)
```

All strings must be NUL-terminated, and `argv` and `envp` must be NULL-terminated pointer arrays.

For example:

```asm
section .rodata
program_path: db "/usr/bin/cc", 0
arg0:         db "cc", 0
arg1:         db "--version", 0

section .data
argv:
    dq arg0
    dq arg1
    dq 0

envp:
    dq 0
```

Then:

```asm
    mov eax, SYS_execve
    lea rdi, [rel program_path]
    lea rsi, [rel argv]
    lea rdx, [rel envp]
    syscall
```

A successful `execve` never returns. The child begins executing the new program at its entry point. If it returns, the syscall failed. ([man7.org][2])

Handle failure with `_exit`, not by returning into normal compiler code:

```asm
.child_failure:
    ; Optionally write an error message to stderr here.
    mov edi, 127
    mov eax, SYS_exit
    syscall
```

Exit code `127` is conventionally used for “could not execute command,” although that convention is yours to adopt.

### Environment variables

Passing:

```asm
envp:
    dq 0
```

gives the child an empty environment.

That may cause unexpected behavior. For example, programs may expect variables such as `PATH`, `HOME`, `LANG`, or `TMPDIR`.

You have three choices:

* Explicitly construct an environment array.
* Preserve the environment originally passed to your program.
* Initially support absolute executable paths only and document the empty environment.

The kernel does not search `PATH`. `execve("cc", ...)` attempts to open exactly a file called `cc` relative to the current directory. Shell-like path lookup must be implemented by your runtime.

## 7. Parent setup

The parent does not need the write ends:

```asm
.parent:
    mov edi, dword [rel stdout_pipe + 4]
    call close_fd

    mov edi, dword [rel stderr_pipe + 4]
    call close_fd
```

It keeps:

```text
stdout_pipe[0]
stderr_pipe[0]
```

## 8. Do not read the pipes sequentially

This approach is unsafe:

```text
read all stdout
read all stderr
```

Suppose the child writes enough data to stderr to fill the stderr pipe while the parent is waiting for stdout. The child blocks writing stderr, and the parent blocks reading stdout. That is a deadlock.

You must drain both pipes concurrently.

The main implementation options are:

* `poll`
* `select`
* `epoll`
* Nonblocking descriptors with a manual loop
* Separate threads

For a small runtime, `poll` is generally the simplest.

## 9. Using `poll`

The kernel representation of `struct pollfd` is:

```c
struct pollfd {
    int   fd;
    short events;
    short revents;
};
```

It is 8 bytes on x86-64:

```text
offset 0: int fd
offset 4: short events
offset 6: short revents
```

Constants:

```asm
POLLIN  equ 1
POLLHUP equ 16
POLLERR equ 8
POLLNVAL equ 32
```

Storage:

```asm
section .bss
pollfds: resb 16             ; two pollfd structures
io_buffer: resb 4096
```

Initialize:

```asm
mov eax, dword [rel stdout_pipe + 0]
mov dword [rel pollfds + 0], eax
mov word  [rel pollfds + 4], POLLIN
mov word  [rel pollfds + 6], 0

mov eax, dword [rel stderr_pipe + 0]
mov dword [rel pollfds + 8], eax
mov word  [rel pollfds + 12], POLLIN
mov word  [rel pollfds + 14], 0
```

Call `poll`:

```asm
mov eax, SYS_poll
lea rdi, [rel pollfds]
mov esi, 2                   ; number of pollfd entries
mov edx, -1                  ; infinite timeout
syscall
```

Afterward, inspect each `revents` field:

```asm
movzx eax, word [rel pollfds + 6]
test eax, POLLIN | POLLHUP | POLLERR
jnz .read_stdout

movzx eax, word [rel pollfds + 14]
test eax, POLLIN | POLLHUP | POLLERR
jnz .read_stderr
```

Even when `POLLHUP` is present, call `read`: there may still be buffered data waiting.

## 10. Reading output

A read looks like:

```asm
; read(stdout_fd, io_buffer, 4096)
mov eax, SYS_read
mov edi, dword [rel stdout_pipe + 0]
lea rsi, [rel io_buffer]
mov edx, 4096
syscall
```

Interpret the result:

```text
rax > 0    that many bytes were read
rax = 0    EOF; all writers are closed
rax < 0    error
```

Do not assume output is text. Preserve a byte array plus its explicit length. Output can contain NUL bytes, invalid UTF-8, or arbitrary binary data.

When `read` returns zero:

1. Close that descriptor.
2. Set its `pollfd.fd` to `-1`.
3. Continue until both streams reach EOF.

For example:

```asm
.stdout_eof:
    mov edi, dword [rel stdout_pipe + 0]
    call close_fd
    mov dword [rel pollfds + 0], -1
```

A negative `pollfd.fd` causes `poll` to ignore that entry.

### Handling `EINTR`

Most blocking syscalls can be interrupted by a signal. In raw syscall code, retry when the result equals `-EINTR`:

```asm
EINTR equ 4

cmp rax, -EINTR
je .retry
```

For nonblocking I/O, also handle:

```asm
EAGAIN equ 11
```

## 11. Waiting for the child

After both pipes reach EOF—or interleaved with the pipe-reading loop—call `wait4`:

```asm
; wait4(child_pid, &status, 0, NULL)
mov eax, SYS_wait4
mov rdi, r12
lea rsi, [rel child_status]
xor edx, edx                 ; options = 0
xor r10d, r10d               ; rusage = NULL
syscall
```

The fourth syscall argument goes in `r10`, not `rcx`.

A successful call returns the child PID. `wait4` writes an encoded integer status to `child_status`; it does not directly write the exit code. Waiting also reaps the child, preventing it from remaining as a zombie. ([man7.org][3])

## 12. Decoding the wait status

Linux uses the traditional Unix wait-status encoding.

Given:

```asm
mov eax, dword [rel child_status]
```

Determine whether the child exited normally:

```text
low 7 bits == 0
```

Then the exit code is:

```text
(status >> 8) & 0xff
```

Assembly:

```asm
mov eax, dword [rel child_status]
mov ecx, eax
and ecx, 0x7f
jnz .terminated_abnormally

shr eax, 8
and eax, 0xff
; eax = normal exit code
```

If the low seven bits are nonzero, they generally contain the terminating signal:

```asm
mov eax, dword [rel child_status]
and eax, 0x7f
; eax = signal number
```

A useful language-level result type would distinguish these cases instead of inventing a normal exit code:

```text
ProcessResult {
    stdout: Bytes,
    stderr: Bytes,
    termination:
        Exited(code: Integer)
        | Signaled(signal: Integer, core_dumped: Boolean)
}
```

The core-dump flag is traditionally bit 7:

```text
(status & 0x80) != 0
```

## 13. Recommended control flow

Conceptually:

```text
run_process(path, argv, envp):
    stdout_pipe = pipe()
    stderr_pipe = pipe()

    pid = fork()

    if pid == 0:
        dup2(stdout_pipe.write, 1)
        dup2(stderr_pipe.write, 2)

        close every original pipe descriptor

        execve(path, argv, envp)
        exit(127)

    close stdout_pipe.write
    close stderr_pipe.write

    stdout = byte_buffer()
    stderr = byte_buffer()

    while stdout_pipe or stderr_pipe remains open:
        poll(open pipe descriptors)

        if stdout readable or hung up:
            repeatedly read available stdout
            append bytes to stdout
            close descriptor on EOF

        if stderr readable or hung up:
            repeatedly read available stderr
            append bytes to stderr
            close descriptor on EOF

    status = wait4(pid)

    return {
        stdout,
        stderr,
        decoded_status
    }
```

## 14. Detecting `execve` failure precisely

Using exit code `127` cannot distinguish:

```text
execve failed
```

from:

```text
the successfully executed program deliberately exited with 127
```

For a robust runtime, create a third pipe called something like `exec_error_pipe`.

Before `fork`, create it with `O_CLOEXEC`:

```text
pipe2(exec_error_pipe, O_CLOEXEC)
```

Child behavior:

1. Keep its write end open.
2. Call `execve`.
3. On failure, write the positive errno value to the pipe and exit.
4. On success, the kernel closes the descriptor automatically because it has `O_CLOEXEC`.

Parent behavior:

* EOF without data means `execve` succeeded.
* An errno integer means `execve` failed.

This lets the API return something such as:

```text
SpawnError(errno)
```

rather than pretending the program ran.

`O_CLOEXEC` is:

```asm
O_CLOEXEC equ 0x80000
```

Create a pipe with flags:

```asm
mov eax, SYS_pipe2
lea rdi, [rel exec_error_pipe]
mov esi, O_CLOEXEC
syscall
```

## 15. File-descriptor inheritance

A child inherits every open file descriptor unless it has the close-on-exec flag. This matters once your compiler becomes larger.

Without proper descriptor management, subprocesses may accidentally inherit:

* Source files
* Object files
* Temporary files
* Listening sockets
* Other subprocess pipes

Prefer creating internal descriptors with `O_CLOEXEC`. Then explicitly duplicate only the descriptors that must survive into the new program.

For stdout:

```asm
; dup3(oldfd, 1, 0)
mov eax, SYS_dup3
mov edi, oldfd
mov esi, 1
xor edx, edx
syscall
```

Do not call `dup3(fd, fd, ...)`; unlike `dup2`, that is an error. Check whether the source already equals the destination.

## 16. Running shell commands

You normally should not invoke a shell. Represent commands as an executable plus argument array:

```text
run("/usr/bin/as", ["as", "-o", "file.o", "file.s"])
```

rather than:

```text
run("as -o file.o file.s")
```

Direct execution avoids quoting problems and shell injection.

When shell syntax is actually desired, explicitly execute a shell:

```text
path = "/bin/sh"
argv = ["sh", "-c", command, null]
```

Then `execve("/bin/sh", argv, envp)`.

## 17. A good initial runtime API

I would separate spawning from collection:

```text
struct ChildProcess {
    pid: Integer
    stdout_fd: Integer
    stderr_fd: Integer
}

spawn(
    executable: String,
    arguments: Array[String],
    environment: Array[String]
) -> Result[ChildProcess, SpawnError]

communicate(
    child: ChildProcess
) -> Result[ProcessResult, IOError]
```

Then add a convenience wrapper:

```text
run(...) -> Result[ProcessResult, ProcessError]
```

This separation later makes it possible to support:

* Streaming output
* Supplying stdin
* Timeouts
* Killing the child
* Pipelines
* Multiple concurrent subprocesses

The core primitive is not really “run a command.” It is:

```text
create pipes → fork → configure child descriptors → execve
             → drain descriptors → wait4
```

That is essentially the foundation on which libc subprocess wrappers are built.

[1]: https://man7.org/linux/man-pages/man2/fork.2.html?utm_source=chatgpt.com "fork(2) - Linux manual page"
[2]: https://man7.org/linux/man-pages/man2/execve.2.html?utm_source=chatgpt.com "execve(2) - Linux manual page"
[3]: https://man7.org/linux/man-pages/man2/wait.2.html?utm_source=chatgpt.com "wait(2) - Linux manual page"
