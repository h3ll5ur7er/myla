// Benchmark (MYLA-242): quicksort with Myla's semantics: the generic sort made
// concrete for int and for a struct whose `cmp` decides `<` and `>`;
// reference-counted lists built by pushes, every index checked, the stack of
// ranges a list too (popping an empty one traps). The lists are moved into
// `sort` (their callers don't use them again), so they are not copied.
#include "../myla_rt.h"

typedef struct { int32_t key, tag; } Pair;

static inline int32_t pair_cmp(Pair a, Pair b) {
    if (a.key != b.key) return a.key < b.key ? -1 : 1;
    return a.tag - b.tag;
}
#define INT_CMP(a, b) ((a) < (b) ? -1 : (a) > (b) ? 1 : 0)
#define PAIR_CMP(a, b) pair_cmp((a), (b))

MYLA_LIST(IntList, int32_t)
MYLA_LIST(PairList, Pair)

static inline int32_t pop(IntList **l) {
    IntList *s = *l;
    if (s->len == 0) myla_trap("pop from an empty list");
    if (s->rc != 1) *l = s = IntList_copy(s);
    return s->items[--s->len];
}

#define DEFINE_SORT(NAME, L, T, CMP)                                         \
    static L *NAME(L *a) {                                                   \
        IntList *stack = IntList_new();                                      \
        IntList_push(&stack, 0);                                             \
        IntList_push(&stack, (int32_t)a->len - 1);                           \
        while (stack->len > 0) {                                             \
            int32_t hi = pop(&stack), lo = pop(&stack);                      \
            if (lo < hi) {                                                   \
                T pivot = L##_get(a, lo + (hi - lo) / 2);                    \
                int32_t i = lo, j = hi;                                      \
                while (i <= j) {                                             \
                    while (CMP(L##_get(a, i), pivot) < 0) i++;               \
                    while (CMP(L##_get(a, j), pivot) > 0) j--;               \
                    if (i <= j) {                                            \
                        T t = L##_get(a, i);                                 \
                        L##_set(&a, i, L##_get(a, j));                       \
                        L##_set(&a, j, t);                                   \
                        i++;                                                 \
                        j--;                                                 \
                    }                                                        \
                }                                                            \
                IntList_push(&stack, lo);                                    \
                IntList_push(&stack, j);                                     \
                IntList_push(&stack, i);                                     \
                IntList_push(&stack, hi);                                    \
            }                                                                \
        }                                                                    \
        IntList_release(stack);                                              \
        return a;                                                            \
    }

DEFINE_SORT(sort_ints, IntList, int32_t, INT_CMP)
DEFINE_SORT(sort_pairs, PairList, Pair, PAIR_CMP)

static IntList *numbers(int32_t n) {
    IntList *out = IntList_new();
    int64_t state = 3;
    for (int32_t i = 0; i < n; i++) {
        state = (state * 1103515245 + 12345) % 2147483648;
        IntList_push(&out, (int32_t)(state >> 4));
    }
    return out;
}

int main(int argc, char **argv) {
    int32_t n = myla_size(argc, argv, 1000000);
    IntList *sorted = sort_ints(numbers(n));
    IntList *xs = numbers(n);
    PairList *pairs = PairList_new();
    for (int64_t i = 0; i < xs->len; i++) PairList_push(&pairs, (Pair){xs->items[i] % 1000, xs->items[i] % 7});
    IntList_release(xs);
    PairList *ps = sort_pairs(pairs);
    int64_t a = 0, b = 0;
    for (int32_t i = 0; i < n; i++) {
        if (i > 0 && (IntList_get(sorted, i - 1) > IntList_get(sorted, i) ||
                      pair_cmp(PairList_get(ps, i - 1), PairList_get(ps, i)) > 0)) { a = b = -1; break; }
        a += (int64_t)IntList_get(sorted, i) * (int64_t)(i % 7);
        b += (int64_t)PairList_get(ps, i).tag * (int64_t)(i % 5);
    }
    printf("%lld\n%lld\n", (long long)a, (long long)b);
    IntList_release(sorted);
    PairList_release(ps);
    return 0;
}
