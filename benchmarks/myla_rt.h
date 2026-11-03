// myla_rt.h: Myla's semantics in C, for the benchmarks' "C with Myla's
// semantics" versions (MYLA-242). They do the work Myla's semantics require,
// written as a good implementation would: a reference count where a value is
// shared or dropped, a bounds check on every index, a copy before a write to
// a list someone else also holds (copy-on-write), wrapping int32 arithmetic
// (compile with -fwrapv), a trap on division by zero. They don't copy what
// Myla's compiler happens to emit beyond that; callgrind shows that part.
#ifndef MYLA_RT_H
#define MYLA_RT_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static inline void myla_trap(const char *msg) {
    fflush(stdout);
    fprintf(stderr, "runtime error: %s\n", msg);
    exit(1);
}

static inline int32_t myla_div(int32_t a, int32_t b) {
    if (b == 0) myla_trap("division by zero");
    if (b == -1) return (int32_t)(0u - (uint32_t)a);    // INT32_MIN / -1 wraps
    return a / b;
}

static inline void *myla_alloc(size_t n) {
    void *p = malloc(n);
    if (!p) myla_trap("out of memory");
    return p;
}

// A list of T: a reference-counted cell. Reads check the index; writes and
// pushes check it, and first copy the list unless this is its only reference.
#define MYLA_LIST(NAME, T)                                                              \
    typedef struct { int64_t rc, len, cap; T *items; } NAME;                            \
    static inline NAME *NAME##_new(void) {                                              \
        NAME *l = myla_alloc(sizeof *l);                                                \
        l->rc = 1; l->len = 0; l->cap = 0; l->items = NULL;                             \
        return l;                                                                       \
    }                                                                                   \
    __attribute__((unused)) static inline void NAME##_retain(NAME *l) { l->rc++; }      \
    static inline void NAME##_release(NAME *l) {                                        \
        if (--l->rc == 0) { free(l->items); free(l); }                                  \
    }                                                                                   \
    static NAME *NAME##_copy(NAME *l) {                                                 \
        NAME *c = myla_alloc(sizeof *c);                                                \
        c->rc = 1; c->len = l->len; c->cap = l->len;                                    \
        c->items = myla_alloc(sizeof(T) * (size_t)(l->len ? l->len : 1));               \
        memcpy(c->items, l->items, sizeof(T) * (size_t)l->len);                         \
        l->rc--;                                                                        \
        return c;                                                                       \
    }                                                                                   \
    static inline T NAME##_get(const NAME *l, int64_t i) {                              \
        if ((uint64_t)i >= (uint64_t)l->len) myla_trap("index out of bounds");          \
        return l->items[i];                                                             \
    }                                                                                   \
    static inline void NAME##_set(NAME **lp, int64_t i, T v) {                          \
        NAME *l = *lp;                                                                  \
        if ((uint64_t)i >= (uint64_t)l->len) myla_trap("index out of bounds");          \
        if (l->rc != 1) *lp = l = NAME##_copy(l);                                       \
        l->items[i] = v;                                                                \
    }                                                                                   \
    static inline void NAME##_push(NAME **lp, T v) {                                    \
        NAME *l = *lp;                                                                  \
        if (l->rc != 1) *lp = l = NAME##_copy(l);                                       \
        if (l->len == l->cap) {                                                         \
            l->cap = l->cap ? l->cap * 2 : 4;                                           \
            l->items = realloc(l->items, sizeof(T) * (size_t)l->cap);                   \
            if (!l->items) myla_trap("out of memory");                                  \
        }                                                                               \
        l->items[l->len++] = v;                                                         \
    }

// The size given as the first argument, or `fallback` (as the Myla programs).
static inline int32_t myla_size(int argc, char **argv, int32_t fallback) {
    if (argc < 2) return fallback;
    char *end;
    long v = strtol(argv[1], &end, 10);
    if (*argv[1] == '\0' || *end != '\0') return fallback;
    return (int32_t)v;
}

#endif
