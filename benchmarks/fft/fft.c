// Benchmark (MYLA-975): the FFT of fft_split.my and fft_complex.my in C,
// operation for operation. Without -DCOMPLEX the signal is two arrays of
// doubles, with it one array of structs. Compile with -ffp-contract=off:
// a fused multiply-add would change the last bits.
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

enum { SEED = 42, IM = 139968, IA = 3877, IC = 29573 };

#ifdef COMPLEX
typedef struct { double re, im; } Complex;
typedef struct { Complex *v; } Signal;
#define RE(s, i) (s).v[i].re
#define IMAG(s, i) (s).v[i].im
#else
typedef struct { double *re, *im; } Signal;
#define RE(s, i) (s).re[i]
#define IMAG(s, i) (s).im[i]
#endif

typedef struct { Signal w; } Plan;

static Signal alloc_signal(int n) {
    Signal s;
#ifdef COMPLEX
    s.v = malloc(n * sizeof(Complex));
#else
    s.re = malloc(n * sizeof(double));
    s.im = malloc(n * sizeof(double));
#endif
    return s;
}

static void free_signal(Signal s) {
#ifdef COMPLEX
    free(s.v);
#else
    free(s.re);
    free(s.im);
#endif
}

static Plan plan(int n) {
    // cos and sin of 2*pi/m for m = 4, 8, ... n, each from the one before
    double cs[32] = { 0.0 }, sn[32] = { 1.0 };
    int level = 0;
    for (int m = 4; m < n; m *= 2, level++) {
        double half = sqrt((1.0 + cs[level]) / 2.0);
        sn[level + 1] = sn[level] / (2.0 * half);
        cs[level + 1] = half;
    }
    // the factor for h + k is the one for k turned by h's angle
    Plan p = { alloc_signal(n / 2) };
    RE(p.w, 0) = 1.0;
    IMAG(p.w, 0) = 0.0;
    for (int h = 1; h < n / 2; h *= 2, level--) {
        double c = cs[level], s = sn[level];
        for (int k = 0; k < h; k++) {
            RE(p.w, h + k) = RE(p.w, k) * c + IMAG(p.w, k) * s;
            IMAG(p.w, h + k) = IMAG(p.w, k) * c - RE(p.w, k) * s;
        }
    }
    return p;
}

static Signal noise(int n) {
    Signal x = alloc_signal(n);
    int seed = SEED;
    for (int i = 0; i < n; i++) {
        seed = (seed * IA + IC) % IM;
        RE(x, i) = (double)seed / (double)IM - 0.5;
        seed = (seed * IA + IC) % IM;
        IMAG(x, i) = (double)seed / (double)IM - 0.5;
    }
    return x;
}

static void transform(Signal x, int n, Plan p, int inverse) {
    for (int i = 1, j = 0; i < n; i++) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) {
            double t = RE(x, i); RE(x, i) = RE(x, j); RE(x, j) = t;
            t = IMAG(x, i); IMAG(x, i) = IMAG(x, j); IMAG(x, j) = t;
        }
    }
    double sign = inverse ? -1.0 : 1.0;
    for (int len = 2; len <= n; len *= 2) {
        int half = len / 2, step = n / len;
        for (int start = 0; start < n; start += len) {
            for (int k = 0; k < half; k++) {
                double wr = RE(p.w, k * step);
                double wi = sign * IMAG(p.w, k * step);
                int a = start + k, b = a + half;
                double vr = RE(x, b) * wr - IMAG(x, b) * wi;
                double vi = RE(x, b) * wi + IMAG(x, b) * wr;
                double ur = RE(x, a), ui = IMAG(x, a);
                RE(x, a) = ur + vr;
                IMAG(x, a) = ui + vi;
                RE(x, b) = ur - vr;
                IMAG(x, b) = ui - vi;
            }
        }
    }
    if (inverse) {
        double scale = 1.0 / (double)n;
        for (int i = 0; i < n; i++) {
            RE(x, i) *= scale;
            IMAG(x, i) *= scale;
        }
    }
}

static double weight(Signal x, int n) {
    double sum = 0.0;
    for (int i = 0; i < n; i++) sum += fabs(RE(x, i)) + fabs(IMAG(x, i));
    return sum;
}

static double distance(Signal x, Signal y, int n) {
    double worst = 0.0;
    for (int i = 0; i < n; i++) {
        double d = fabs(RE(x, i) - RE(y, i)) + fabs(IMAG(x, i) - IMAG(y, i));
        if (d > worst) worst = d;
    }
    return worst;
}

static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}

// Times `rounds` round trips of `n` points, without the table and the input.
static void run(int n, int rounds) {
    Plan p = plan(n);
    Signal input = noise(n), x = noise(n);
    double start = now();
    long long checksum = 0;
    for (int r = 0; r < rounds; r++) {
        transform(x, n, p, 0);
        if (r == 0) checksum = (long long)(weight(x, n) * 1000.0);
        transform(x, n, p, 1);
    }
    long long error = (long long)(distance(x, input, n) * 1e15);
    double secs = now() - start;
    free_signal(x);
    free_signal(input);
    free_signal(p.w);
    printf("fft-%d %lld %lld %d %.6f\n", n, checksum, error, rounds, secs);
}

//   fft [points rounds]
int main(int argc, char **argv) {
    if (argc == 3) {
        run(atoi(argv[1]), atoi(argv[2]));
        return 0;
    }
    run(4096, 10000);
    run(1 << 20, 10);
    return 0;
}
