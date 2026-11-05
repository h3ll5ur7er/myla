# host.sh — sourced by bootstrap.sh, check-seed.sh and update-seed.sh: the
# machine the toolchain is built on, its seed and its tools (MYLA-276, D127).
#
# The toolchain bootstraps from a seed of its own assembly for the machine
# it runs on, assembled and linked by that machine's GNU binutils: x86-64
# and aarch64 Linux (a Raspberry Pi 4 or 5 with a 64-bit OS, an ARM server).
# The compiler it builds targets that machine by default.
#
# Overrides, for testing another machine's bootstrap here:
#   MYLA_ARCH  the machine's architecture, x86_64 or aarch64 (`uname -m`)
#   AS, LD     its GNU assembler and linker (`as`, `ld`; for aarch64 on an
#              x86-64 machine: aarch64-linux-gnu-as and aarch64-linux-gnu-ld)
#   MYLA_RUN   what the built tools run under (an emulator: qemu-aarch64)
#
# Sets HOST_TARGET (the target it builds for by default, as `--target`
# names it), HOST_SEED, SEEDS (every target with a seed, `target:file`), and
# defines asm_to_bin and run_tool.

case "$(uname -s)" in
    Linux) ;;
    *)
        echo "FAIL: Myla's toolchain builds on Linux (x86-64 or aarch64) so far; macOS and Windows are MYLA-164 and MYLA-165" >&2
        exit 1 ;;
esac

case "${MYLA_ARCH:-$(uname -m)}" in
    x86_64 | amd64)
        HOST_TARGET="x86_64-linux" ;;
    aarch64 | arm64)
        HOST_TARGET="aarch64-linux" ;;
    armv6l | armv7l | armv8l | arm*)
        echo "FAIL: 32-bit ARM isn't a target; on a Raspberry Pi use a 64-bit OS (\`uname -m\` says aarch64 there)" >&2
        exit 1 ;;
    *)
        echo "FAIL: no seed for this machine ($(uname -m)); the seeds are for x86_64 and aarch64" >&2
        exit 1 ;;
esac

# every seed: the compiler at its fixed point, as its own target's assembly
SEEDS="x86_64-linux:bootstrap/seed.s aarch64-linux:bootstrap/seed-aarch64.s"

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

AS="${AS:-as}"
LD="${LD:-ld}"
for tool in "$AS" "$LD"; do
    if ! command -v "$tool" > /dev/null 2>&1; then
        echo "FAIL: '$tool' not found: the bootstrap needs GNU as and ld (binutils; on Debian, Ubuntu and Raspberry Pi OS: sudo apt install binutils)" >&2
        exit 1
    fi
done

# Assemble + link a generated .s into a static, libc-free executable for
# this machine.
asm_to_bin() {  # <src.s> <out-bin>
    if [ "$HOST_TARGET" = "x86_64-linux" ]; then
        "$AS" --64 -o "${2}.o" "$1"
    else
        "$AS" -o "${2}.o" "$1"
    fi
    "$LD" -o "$2" "${2}.o"
}

# Run a tool the bootstrap built (under MYLA_RUN when set).
run_tool() {  # <binary> [args...]
    if [ -n "${MYLA_RUN:-}" ]; then
        $MYLA_RUN "$@"
    else
        "$@"
    fi
}
