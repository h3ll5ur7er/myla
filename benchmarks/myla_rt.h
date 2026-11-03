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
    __attribute__((unused)) static inline NAME *NAME##_new(void) {                                              \
        NAME *l = myla_alloc(sizeof *l);                                                \
        l->rc = 1; l->len = 0; l->cap = 0; l->items = NULL;                             \
        return l;                                                                       \
    }                                                                                   \
    __attribute__((unused)) static inline void NAME##_retain(NAME *l) { l->rc++; }      \
    __attribute__((unused)) static inline void NAME##_release(NAME *l) {                                        \
        if (--l->rc == 0) { free(l->items); free(l); }                                  \
    }                                                                                   \
    __attribute__((unused)) static NAME *NAME##_copy(NAME *l) {                                                 \
        NAME *c = myla_alloc(sizeof *c);                                                \
        c->rc = 1; c->len = l->len; c->cap = l->len;                                    \
        c->items = myla_alloc(sizeof(T) * (size_t)(l->len ? l->len : 1));               \
        memcpy(c->items, l->items, sizeof(T) * (size_t)l->len);                         \
        l->rc--;                                                                        \
        return c;                                                                       \
    }                                                                                   \
    __attribute__((unused)) static inline T NAME##_get(const NAME *l, int64_t i) {                              \
        if ((uint64_t)i >= (uint64_t)l->len) myla_trap("index out of bounds");          \
        return l->items[i];                                                             \
    }                                                                                   \
    __attribute__((unused)) static inline void NAME##_set(NAME **lp, int64_t i, T v) {                          \
        NAME *l = *lp;                                                                  \
        if ((uint64_t)i >= (uint64_t)l->len) myla_trap("index out of bounds");          \
        if (l->rc != 1) *lp = l = NAME##_copy(l);                                       \
        l->items[i] = v;                                                                \
    }                                                                                   \
    __attribute__((unused)) static inline void NAME##_push(NAME **lp, T v) {                                    \
        NAME *l = *lp;                                                                  \
        if (l->rc != 1) *lp = l = NAME##_copy(l);                                       \
        if (l->len == l->cap) {                                                         \
            l->cap = l->cap ? l->cap * 2 : 4;                                           \
            l->items = realloc(l->items, sizeof(T) * (size_t)l->cap);                   \
            if (!l->items) myla_trap("out of memory");                                  \
        }                                                                               \
        l->items[l->len++] = v;                                                         \
    }

// A string: a reference-counted cell of bytes (a Myla `str` is immutable).
typedef struct { int64_t rc, len; char bytes[]; } MylaStr;

__attribute__((unused)) static MylaStr *mstr_new(const char *bytes, int64_t len) {
    MylaStr *s = myla_alloc(sizeof *s + (size_t)len + 1);
    s->rc = 1;
    s->len = len;
    memcpy(s->bytes, bytes, (size_t)len);
    s->bytes[len] = '\0';
    return s;
}

__attribute__((unused)) static inline void mstr_release(MylaStr *s) {
    if (--s->rc == 0) free(s);
}

// `a + b`: a new string.
__attribute__((unused)) static MylaStr *mstr_concat(const MylaStr *a, const MylaStr *b) {
    MylaStr *s = myla_alloc(sizeof *s + (size_t)(a->len + b->len) + 1);
    s->rc = 1;
    s->len = a->len + b->len;
    memcpy(s->bytes, a->bytes, (size_t)a->len);
    memcpy(s->bytes + a->len, b->bytes, (size_t)b->len + 1);
    return s;
}

// `format("{}", v)` of an integer: a new string.
__attribute__((unused)) static MylaStr *mstr_int(int64_t v) {
    char buf[24];
    int n = snprintf(buf, sizeof buf, "%lld", (long long)v);
    return mstr_new(buf, n);
}

// The byte at `i`, checked.
__attribute__((unused)) static inline uint8_t mstr_at(const MylaStr *s, int64_t i) {
    if ((uint64_t)i >= (uint64_t)s->len) myla_trap("index out of bounds");
    return (uint8_t)s->bytes[i];
}

// A StringBuilder: a growable buffer; `build` copies it into a new string.
typedef struct { int64_t len, cap; char *bytes; } MylaBuilder;

__attribute__((unused)) static void mb_append(MylaBuilder *b, const char *bytes, int64_t len) {
    if (b->len + len > b->cap) {
        while (b->len + len > b->cap) b->cap = b->cap ? b->cap * 2 : 16;
        b->bytes = realloc(b->bytes, (size_t)b->cap);
        if (!b->bytes) myla_trap("out of memory");
    }
    memcpy(b->bytes + b->len, bytes, (size_t)len);
    b->len += len;
}

__attribute__((unused)) static MylaStr *mb_build(const MylaBuilder *b) {
    return mstr_new(b->bytes ? b->bytes : "", b->len);
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
