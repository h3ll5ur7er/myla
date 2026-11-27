# host.sh — sourced by bootstrap.sh, check-seed.sh and update-seed.sh: the
# machine the toolchain is built on, its seed and its tools (MYLA-276, D127,
# MYLA-709).
#
# The toolchain bootstraps from a seed of its own assembly for the machine
# it runs on: x86-64 and aarch64 Linux (a Raspberry Pi 4 or 5 with a 64-bit
# OS, an ARM server), assembled and linked by that machine's GNU binutils;
# and x86-64 Windows under Git Bash (D214), by LLVM's clang, llvm-dlltool
# and lld-link (D211), as `myla build --target x86_64-windows` does. The
# compiler it builds targets that machine by default.
#
# Overrides, for testing another machine's bootstrap here:
#   MYLA_OS    the machine's system, linux or windows (`uname -s`: Linux;
#              MINGW64_NT-…, MSYS_NT-… under Git Bash)
#   MYLA_ARCH  the machine's architecture, x86_64 or aarch64 (`uname -m`)
#   AS, LD     its assembler and linker (`as`, `ld`; for aarch64 on an
#              x86-64 machine: aarch64-linux-gnu-as and aarch64-linux-gnu-ld;
#              on Windows `clang` and `lld-link`)
#   DLLTOOL    what makes Windows' import libraries (`llvm-dlltool`)
#   MYLA_RUN   what the built tools run under (an emulator: qemu-aarch64;
#              for Windows' on Linux, Wine: MYLA_OS=windows MYLA_RUN=wine64,
#              with Wine's server and services started first, `wineserver
#              -p` and `wine64 wineboot`, so that they don't hold the tools'
#              pipes)
#
# Sets HOST_OS (linux or windows), HOST_TARGET (the target it builds for by
# default, as `--target` names it), HOST_SEED, EXE (the programs' suffix:
# ".exe" on Windows, else ""), SEEDS (every target with a seed,
# `target:file`), and defines asm_to_bin and run_tool.

case "${MYLA_OS:-$(uname -s)}" in
    Linux | linux)
        HOST_OS="linux" ;;
    MINGW* | MSYS* | windows)
        HOST_OS="windows" ;;
    *)
        echo "FAIL: Myla's toolchain builds on Linux (x86-64 or aarch64) and on x86-64 Windows (under Git Bash) so far; macOS is MYLA-164" >&2
        exit 1 ;;
esac

case "$HOST_OS:${MYLA_ARCH:-$(uname -m)}" in
    linux:x86_64 | linux:amd64)
        HOST_TARGET="x86_64-linux" ;;
    linux:aarch64 | linux:arm64)
        HOST_TARGET="aarch64-linux" ;;
    windows:x86_64 | windows:amd64)
        HOST_TARGET="x86_64-windows" ;;
    linux:armv6l | linux:armv7l | linux:armv8l | linux:arm*)
        echo "FAIL: 32-bit ARM isn't a target; on a Raspberry Pi use a 64-bit OS (\`uname -m\` says aarch64 there)" >&2
        exit 1 ;;
    windows:*)
        echo "FAIL: no seed for this machine (${MYLA_ARCH:-$(uname -m)} Windows); the Windows seed is x86_64's" >&2
        exit 1 ;;
    *)
        echo "FAIL: no seed for this machine ($(uname -m)); the seeds are for x86_64 and aarch64" >&2
        exit 1 ;;
esac

# every seed: the compiler at its fixed point, as its own target's assembly
SEEDS="x86_64-linux:bootstrap/seed.s aarch64-linux:bootstrap/seed-aarch64.s x86_64-windows:bootstrap/seed-windows.s"

seed_of() {  # <target> -> its seed's path
    local entry
    for entry in $SEEDS; do
        if [ "${entry%%:*}" = "$1" ]; then
            echo "${entry#*:}"
            return
        fi
    done
}

HOST_SEED="$(seed_of "$HOST_TARGET")"

if [ "$HOST_OS" = windows ]; then
    EXE=".exe"
    AS="${AS:-clang}"
    LD="${LD:-lld-link}"
    DLLTOOL="${DLLTOOL:-llvm-dlltool}"
    for tool in "$AS" "$DLLTOOL" "$LD"; do
        if ! command -v "$tool" > /dev/null 2>&1; then
            echo "FAIL: '$tool' not found: the bootstrap on Windows needs LLVM's clang, llvm-dlltool and lld-link on PATH (D211; LLVM for Windows installs them in C:\\Program Files\\LLVM\\bin: export PATH=\"/c/Program Files/LLVM/bin:\$PATH\")" >&2
            exit 1
        fi
    done
else
    EXE=""
    AS="${AS:-as}"
    LD="${LD:-ld}"
    for tool in "$AS" "$LD"; do
        if ! command -v "$tool" > /dev/null 2>&1; then
            echo "FAIL: '$tool' not found: the bootstrap needs GNU as and ld (binutils; on Debian, Ubuntu and Raspberry Pi OS: sudo apt install binutils)" >&2
            exit 1
        fi
    done
fi

# Assemble + link a generated .s into a static, libc-free executable for
# this machine (on Windows `<out-bin>` is the .exe's name).
asm_to_bin() {  # <src.s> <out-bin>
    case "$HOST_TARGET" in
        x86_64-windows)
            windows_asm_to_bin "$1" "$2"
            return ;;
        x86_64-linux)
            "$AS" --64 -o "${2}.o" "$1" ;;
        *)
            "$AS" -o "${2}.o" "$1" ;;
    esac
    "$LD" -o "$2" "${2}.o"
}

# A path as a Windows program reads it: Git Bash's /c/… is C:/… (cygpath);
# a relative path, and any path where there is no cygpath (Wine reads a
# Unix path), as it is.
native_path() {  # <path>
    case "$1" in
        /*)
            if command -v cygpath > /dev/null 2>&1; then
                cygpath -m "$1"
                return
            fi ;;
    esac
    printf '%s\n' "$1"
}

# Windows' build of a .s by the steps and command lines of `myla build
# --target x86_64-windows` (selfhost/driver.my's cmd_build, the tools of
# selfhost/target.my; D211, D212, MYLA-722; tests/burn/test_windows.py
# holds the two to the same): clang assembles it into `<out>.o`; for each
# system DLL it calls, which the assembly's last lines name with the
# functions it calls of it (`# import <dll> <function>…`), `<out>.<dll>.def`
# lists them and llvm-dlltool makes `<out>.<dll>.lib` of it; lld-link links
# the object with them all. Git Bash's conversion of the arguments that look
# like paths is off for the three (MSYS_NO_PATHCONV, MSYS2_ARG_CONV_EXCL):
# it would take lld-link's `/nologo` and `/out:` for paths.
windows_asm_to_bin() {  # <src.s> <out.exe>
    local asm="$1" out="$2" line dll name stem
    local words=() libs=()
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
        "$AS" --target=x86_64-pc-windows-msvc -c -o "$(native_path "${out}.o")" "$(native_path "$asm")"
    while IFS= read -r line; do
        read -r -a words <<< "$line"
        dll="${words[2]}"
        stem="${out}.${dll%.dll}"
        {
            printf 'LIBRARY %s\nEXPORTS\n' "$dll"
            for name in "${words[@]:3}"; do printf '%s\n' "$name"; done
        } > "${stem}.def"
        MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
            "$DLLTOOL" -m i386:x86-64 -d "$(native_path "${stem}.def")" -l "$(native_path "${stem}.lib")"
        libs+=("$(native_path "${stem}.lib")")
    done < <(grep '^# import ' "$asm")
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
        "$LD" /nologo /Brepro /subsystem:console /entry:_start /nodefaultlib /stack:125829120 \
        "/out:$(native_path "$out")" "$(native_path "${out}.o")" "${libs[@]}"
}

# Run a tool the bootstrap built (under MYLA_RUN when set).
run_tool() {  # <binary> [args...]
    if [ -n "${MYLA_RUN:-}" ]; then
        $MYLA_RUN "$@"
    else
        "$@"
    fi
}

# The compiler as its seed carries it (MYLA-431): selfhost/gen_main.my
# compiled by <compiler> for <target> with an empty embedded standard library
# in place of selfhost/embedded_std.my. The bootstrap gives every stage `lib`,
# so stage 0 never reads the library it embeds, which was over half of each
# seed; the stages it builds embed the whole library again. It compiles a
# copy of selfhost/ in a directory of its own, beside a link to lib/ (on
# Windows a copy of it, MYLA-709), by the same relative paths (which the
# positions of runtime errors carry), so the working tree is never changed,
# not even while it runs (MYLA-552).
seed_compile() {  # <compiler> <target> <out.s>
    local compiler="$1" target="$2" out="$3" work f rc=0
    case "$compiler" in /*) ;; *) compiler="$PWD/$compiler" ;; esac
    case "$out" in /*) ;; *) out="$PWD/$out" ;; esac
    work="$(mktemp -d "${TMPDIR:-/tmp}/myla-seed.XXXXXX")"
    mkdir "$work/selfhost"
    for f in selfhost/*.my; do
        if [ "$f" != selfhost/embedded_std.my ]; then cp "$f" "$work/selfhost/"; fi
    done
    if [ "$HOST_OS" = windows ]; then
        # Git Bash's `ln -s` copies, or makes a link that Windows programs
        # can't follow (MSYS' `winsymlinks`)
        cp -R "$PWD/lib" "$work/lib"
    else
        ln -s "$PWD/lib" "$work/lib"
    fi
    cat > "$work/selfhost/embedded_std.my" <<'STUB'
// embedded_std.my as the seeds carry it (MYLA-431): no files. Written in a
// copy of selfhost/ by scripts/host.sh's seed_compile; the bootstrap gives
// stage 0 the library under lib/.

pub fun embedded_paths() -> [str] {
    return []
}

pub fun embedded_file(path: str) -> str {
    return ""
}

pub fun embedded_cache(path: str) -> str {
    return ""
}
STUB
    if [ "$target" = "$HOST_TARGET" ]; then
        (cd "$work" && run_tool "$compiler" selfhost/gen_main.my lib) > "$out" || rc=$?
    else
        (cd "$work" && run_tool "$compiler" selfhost/gen_main.my lib --target "$target") > "$out" || rc=$?
    fi
    rm -rf "$work"
    return $rc
}
