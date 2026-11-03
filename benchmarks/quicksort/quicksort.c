// Benchmark (MYLA-242): quicksort, idiomatic C: the algorithm written once as
// a macro and made concrete for int and for a struct (as monomorphization
// does), arrays, an explicit stack of ranges.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct { int key, tag; } Pair;

static inline int pair_cmp(Pair a, Pair b) {
    if (a.key != b.key) return a.key < b.key ? -1 : 1;
    return a.tag - b.tag;
}
#define INT_CMP(a, b) ((a) < (b) ? -1 : (a) > (b) ? 1 : 0)
#define PAIR_CMP(a, b) pair_cmp((a), (b))

#define DEFINE_SORT(NAME, T, CMP)                                            \
    static void NAME(T *a, int n) {                                          \
        int cap = 64, top = 0;                                               \
        int *stack = malloc(sizeof(int) * (size_t)cap);                      \
        stack[top++] = 0;                                                    \
        stack[top++] = n - 1;                                                \
        while (top > 0) {                                                    \
            int hi = stack[--top], lo = stack[--top];                        \
            if (lo >= hi) continue;                                          \
            T pivot = a[lo + (hi - lo) / 2];                                 \
            int i = lo, j = hi;                                              \
            while (i <= j) {                                                 \
                while (CMP(a[i], pivot) < 0) i++;                            \
                while (CMP(a[j], pivot) > 0) j--;                            \
                if (i <= j) { T t = a[i]; a[i] = a[j]; a[j] = t; i++; j--; } \
            }                                                                \
            if (top + 4 > cap) {                                             \
                cap *= 2;                                                    \
                stack = realloc(stack, sizeof(int) * (size_t)cap);           \
            }                                                                \
            stack[top++] = lo; stack[top++] = j;                             \
            stack[top++] = i; stack[top++] = hi;                             \
        }                                                                    \
        free(stack);                                                         \
    }

DEFINE_SORT(sort_ints, int, INT_CMP)
DEFINE_SORT(sort_pairs, Pair, PAIR_CMP)

static int *numbers(int n) {
    int *out = malloc(sizeof(int) * (size_t)(n ? n : 1));
    int64_t state = 3;
    for (int i = 0; i < n; i++) {
        state = (state * 1103515245 + 12345) % 2147483648;
        out[i] = (int)(state >> 4);
    }
    return out;
}

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 1000000;
    int *sorted = numbers(n);
    sort_ints(sorted, n);
    int *xs = numbers(n);
    Pair *ps = malloc(sizeof(Pair) * (size_t)(n ? n : 1));
    for (int i = 0; i < n; i++) ps[i] = (Pair){xs[i] % 1000, xs[i] % 7};
    sort_pairs(ps, n);
    int64_t a = 0, b = 0;
    for (int i = 0; i < n; i++) {
        if (i > 0 && (sorted[i - 1] > sorted[i] || pair_cmp(ps[i - 1], ps[i]) > 0)) { a = b = -1; break; }
        a += (int64_t)sorted[i] * (i % 7);
        b += (int64_t)ps[i].tag * (i % 5);
    }
    printf("%lld\n%lld\n", (long long)a, (long long)b);
    free(sorted);
    free(xs);
    free(ps);
    return 0;
}
