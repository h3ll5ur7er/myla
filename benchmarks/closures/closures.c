// Benchmark (MYLA-242): closures and pipelines, idiomatic C: a closure is a
// function pointer and a context; map and filter build new arrays.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct { int *items; size_t len, cap; } Vec;
typedef struct { int (*fn)(const void *, int); const void *env; } IntFn;
typedef struct { int64_t (*fn)(const void *, int64_t, int); const void *env; } FoldFn;

static void push(Vec *v, int x) {
    if (v->len == v->cap) { v->cap = v->cap ? v->cap * 2 : 4; v->items = realloc(v->items, v->cap * sizeof(int)); }
    v->items[v->len++] = x;
}

static Vec map_list(Vec xs, IntFn f) {
    Vec out = {0};
    for (size_t i = 0; i < xs.len; i++) push(&out, f.fn(f.env, xs.items[i]));
    return out;
}

static Vec filter_list(Vec xs, IntFn keep) {
    Vec out = {0};
    for (size_t i = 0; i < xs.len; i++) if (keep.fn(keep.env, xs.items[i])) push(&out, xs.items[i]);
    return out;
}

static int64_t fold(Vec xs, int64_t start, FoldFn f) {
    int64_t acc = start;
    for (size_t i = 0; i < xs.len; i++) acc = f.fn(f.env, acc, xs.items[i]);
    return acc;
}

static int add_k(const void *env, int x) { return x + *(const int *)env; }
static int times3(const void *env, int x) { (void)env; return x * 3 % 1000; }
static int odd(const void *env, int x) { (void)env; return x % 2 == 1; }
static int64_t weighted(const void *env, int64_t acc, int x) { return acc + (int64_t)x * *(const int64_t *)env; }

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 1000000;
    Vec xs = {0};
    for (int i = 0; i < n; i++) push(&xs, i);
    int64_t total = 0;
    for (int round = 0; round < 10; round++) {
        int64_t weight = round + 1;
        Vec a = map_list(xs, (IntFn){add_k, &round});
        Vec b = map_list(a, (IntFn){times3, NULL});
        Vec c = filter_list(b, (IntFn){odd, NULL});
        total = fold(c, total, (FoldFn){weighted, &weight});
        free(a.items);
        free(b.items);
        free(c.items);
    }
    printf("%lld\n", (long long)total);
    free(xs.items);
    return 0;
}
