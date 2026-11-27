"""Benchmark (MYLA-545): the FFT of fft_split.my and fft_complex.my in plain
Python, operation for operation: no NumPy, only the built-in float, complex
and list.

    python3 fft.py split|complex [points rounds]

`split` keeps two lists of floats, `complex` one list of the built-in complex
(whose product is ac - bd, ad + bc, the order the other versions use).
"""
import sys
import time
from math import sqrt

SEED = 42
IM = 139968
IA = 3877
IC = 29573


def roots(n):
    """cos and sin of 2π/m for m = 4, 8, … n, each from the one before."""
    cs, sn = [0.0], [1.0]
    m = 4
    while m < n:
        half = sqrt((1.0 + cs[-1]) / 2.0)
        sn.append(sn[-1] / (2.0 * half))
        cs.append(half)
        m *= 2
    return cs, sn


def lcg(n):
    seed = SEED
    for _ in range(n):
        seed = (seed * IA + IC) % IM
        re = seed / IM - 0.5
        seed = (seed * IA + IC) % IM
        yield re, seed / IM - 0.5


def bit_reversed_pairs(n):
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            yield i, j


class Split:
    """The signal as two lists of floats."""

    @staticmethod
    def plan(n):
        cs, sn = roots(n)
        wr, wi = [1.0], [0.0]
        level = len(cs) - 1
        h = 1
        while h < n // 2:
            c, s = cs[level], sn[level]
            for k in range(h):
                wr.append(wr[k] * c + wi[k] * s)
                wi.append(wi[k] * c - wr[k] * s)
            h *= 2
            level -= 1
        return wr, wi

    @staticmethod
    def noise(n):
        pairs = list(lcg(n))
        return [re for re, _ in pairs], [im for _, im in pairs]

    @staticmethod
    def copy(x):
        return x[0][:], x[1][:]

    @staticmethod
    def transform(x, plan, inverse):
        re, im = x
        pwr, pwi = plan
        n = len(re)
        for i, j in bit_reversed_pairs(n):
            re[i], re[j] = re[j], re[i]
            im[i], im[j] = im[j], im[i]
        sign = -1.0 if inverse else 1.0
        length = 2
        while length <= n:
            half = length // 2
            step = n // length
            for start in range(0, n, length):
                for k in range(half):
                    wr = pwr[k * step]
                    wi = sign * pwi[k * step]
                    a = start + k
                    b = a + half
                    vr = re[b] * wr - im[b] * wi
                    vi = re[b] * wi + im[b] * wr
                    ur = re[a]
                    ui = im[a]
                    re[a] = ur + vr
                    im[a] = ui + vi
                    re[b] = ur - vr
                    im[b] = ui - vi
            length *= 2
        if inverse:
            scale = 1.0 / n
            for i in range(n):
                re[i] *= scale
                im[i] *= scale

    @staticmethod
    def weight(x):
        total = 0.0
        for re, im in zip(*x):
            total += abs(re) + abs(im)
        return total

    @staticmethod
    def distance(x, y):
        worst = 0.0
        for i in range(len(x[0])):
            d = abs(x[0][i] - y[0][i]) + abs(x[1][i] - y[1][i])
            if d > worst:
                worst = d
        return worst


class Complex:
    """The signal as one list of complex numbers."""

    @staticmethod
    def plan(n):
        cs, sn = roots(n)
        w = [complex(1.0, 0.0)]
        level = len(cs) - 1
        h = 1
        while h < n // 2:
            c, s = cs[level], -sn[level]
            for k in range(h):
                w.append(complex(w[k].real * c - w[k].imag * s, w[k].imag * c + w[k].real * s))
            h *= 2
            level -= 1
        return w

    @staticmethod
    def noise(n):
        return [complex(re, im) for re, im in lcg(n)]

    @staticmethod
    def copy(x):
        return x[:]

    @staticmethod
    def transform(x, w, inverse):
        n = len(x)
        for i, j in bit_reversed_pairs(n):
            x[i], x[j] = x[j], x[i]
        sign = -1.0 if inverse else 1.0
        length = 2
        while length <= n:
            half = length // 2
            step = n // length
            for start in range(0, n, length):
                for k in range(half):
                    a = start + k
                    b = a + half
                    factor = w[k * step]
                    v = x[b] * complex(factor.real, sign * factor.imag)
                    u = x[a]
                    x[a] = u + v
                    x[b] = u - v
            length *= 2
        if inverse:
            scale = 1.0 / n
            for i in range(n):
                x[i] = complex(x[i].real * scale, x[i].imag * scale)

    @staticmethod
    def weight(x):
        total = 0.0
        for z in x:
            total += abs(z.real) + abs(z.imag)
        return total

    @staticmethod
    def distance(x, y):
        worst = 0.0
        for a, b in zip(x, y):
            d = abs(a.real - b.real) + abs(a.imag - b.imag)
            if d > worst:
                worst = d
        return worst


def run(layout, n, rounds):
    """Times `rounds` round trips of `n` points, without the table and the input."""
    plan = layout.plan(n)
    source = layout.noise(n)
    x = layout.copy(source)
    start = time.perf_counter()
    checksum = 0
    for r in range(rounds):
        layout.transform(x, plan, False)
        if r == 0:
            checksum = int(layout.weight(x) * 1000.0)
        layout.transform(x, plan, True)
    error = int(layout.distance(x, source) * 1e15)
    secs = time.perf_counter() - start
    print(f"fft-{n} {checksum} {error} {rounds} {secs:.6f}")


def main():
    layout = {"split": Split, "complex": Complex}[sys.argv[1]]
    if len(sys.argv) == 4:
        run(layout, int(sys.argv[2]), int(sys.argv[3]))
    else:
        run(layout, 4096, 50)
        run(layout, 1 << 20, 1)


if __name__ == "__main__":
    main()
