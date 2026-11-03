// Benchmark (MYLA-242): closures and pipelines with Myla's semantics: lists
// are reference-counted and built by checked pushes; a closure that captures
// (the partial application, the weighting lambda) has a reference-counted
// environment, made per round; `for x in xs` reads without index checks, as
// a good implementation does.
#include "../myla_rt.h"

MYLA_LIST(IntList, int32_t)

typedef struct { int64_t rc; } Env;
typedef struct { int32_t (*fn)(const Env *, int32_t); Env *env; } IntFn;
typedef struct { int64_t (*fn)(const Env *, int64_t, int32_t); Env *env; } FoldFn;
typedef struct { Env head; int32_t k; } KEnv;
typedef struct { Env head; int64_t weight; } WEnv;

static inline void env_release(Env *e) { if (e && --e->rc == 0) free(e); }

static IntList *map_list(const IntList *xs, IntFn f) {
    IntList *out = IntList_new();
    for (int64_t i = 0; i < xs->len; i++) IntList_push(&out, f.fn(f.env, xs->items[i]));
    return out;
}

static IntList *filter_list(const IntList *xs, IntFn keep) {
    IntList *out = IntList_new();
    for (int64_t i = 0; i < xs->len; i++) if (keep.fn(keep.env, xs->items[i])) IntList_push(&out, xs->items[i]);
    return out;
}

static int64_t fold(const IntList *xs, int64_t start, FoldFn f) {
    int64_t acc = start;
    for (int64_t i = 0; i < xs->len; i++) acc = f.fn(f.env, acc, xs->items[i]);
    return acc;
}

static int32_t add_k(const Env *env, int32_t x) { return x + ((const KEnv *)env)->k; }
static int32_t times3(const Env *env, int32_t x) { (void)env; return x * 3 % 1000; }
static int32_t odd(const Env *env, int32_t x) { (void)env; return x % 2 == 1; }
static int64_t weighted(const Env *env, int64_t acc, int32_t x) { return acc + (int64_t)x * ((const WEnv *)env)->weight; }

int main(int argc, char **argv) {
    int32_t n = myla_size(argc, argv, 1000000);
    IntList *xs = IntList_new();
    for (int32_t i = 0; i < n; i++) IntList_push(&xs, i);
    int64_t total = 0;
    for (int32_t round = 0; round < 10; round++) {
        int64_t weight = (int64_t)(round + 1);
        KEnv *k = myla_alloc(sizeof *k);
        k->head.rc = 1;
        k->k = round;
        IntList *a = map_list(xs, (IntFn){add_k, &k->head});
        env_release(&k->head);
        IntList *b = map_list(a, (IntFn){times3, NULL});
        IntList_release(a);
        IntList *c = filter_list(b, (IntFn){odd, NULL});
        IntList_release(b);
        WEnv *w = myla_alloc(sizeof *w);
        w->head.rc = 1;
        w->weight = weight;
        total = fold(c, total, (FoldFn){weighted, &w->head});
        env_release(&w->head);
        IntList_release(c);
    }
    printf("%lld\n", (long long)total);
    IntList_release(xs);
    return 0;
}
