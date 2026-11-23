#!/usr/bin/env bash
# run.sh [runs]: builds the FFT in Myla (two layouts) and in C (the same two,
# gcc -O2 and -O3 -march=native), checks that all print the same checksums and
# errors, and prints each one's median seconds per size (MYLA-545).
# Run from anywhere; needs build/myla (scripts/bootstrap.sh) and gcc.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(dirname "$(dirname "$here")")"
out="$repo/build/bench/fft"
runs="${1:-5}"
mkdir -p "$out"

"$repo/build/myla" build "$here/fft_split.my" -o "$out/myla_split"
"$repo/build/myla" build "$here/fft_complex.my" -o "$out/myla_complex"
cflags="-ffp-contract=off"
gcc -O2 $cflags "$here/fft.c" -o "$out/c_split_O2" -lm
gcc -O2 $cflags -DCOMPLEX "$here/fft.c" -o "$out/c_complex_O2" -lm
gcc -O3 -march=native $cflags "$here/fft.c" -o "$out/c_split_O3" -lm
gcc -O3 -march=native $cflags -DCOMPLEX "$here/fft.c" -o "$out/c_complex_O3" -lm

pin=()
if command -v taskset >/dev/null && [ "$(nproc)" -gt 1 ]; then pin=(taskset -c "$(($(nproc) - 1))"); fi

results="$out/results.txt"
: > "$results"
for v in c_split_O2 c_complex_O2 c_split_O3 c_complex_O3 myla_split myla_complex; do
    for _ in $(seq "$runs"); do
        "${pin[@]}" "$out/$v" | sed "s/^/$v /" >> "$results"
    done
done

python3 - "$results" <<'PY'
import statistics
import sys

times, answers, variants, sizes = {}, {}, [], []
for line in open(sys.argv[1]):
    variant, size, checksum, error, secs = line.split()
    times.setdefault((variant, size), []).append(float(secs))
    answers.setdefault(size, set()).add((checksum, error))
    if variant not in variants: variants.append(variant)
    if size not in sizes: sizes.append(size)
med = {k: statistics.median(v) for k, v in times.items()}
print(f"{'variant':<14}" + "".join(f" {size:>13}  x C -O2" for size in sizes))
for v in variants:
    base = "c_complex_O2" if "complex" in v else "c_split_O2"
    print(f"{v:<14}" + "".join(f" {med[v, s]:>11.3f} s  {med[v, s] / med[base, s]:>7.2f}" for s in sizes))
bad = [s for s in sizes if len(answers[s]) != 1]
if bad:
    sys.exit("MISMATCH in " + ", ".join(bad))
print("All checksums and errors identical: " + ", ".join(f"{s} {' '.join(next(iter(answers[s])))}" for s in sizes))
PY
