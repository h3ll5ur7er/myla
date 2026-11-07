// Benchmark (MYLA-310): removing keys from a map with Myla's semantics. The
// map of map_remove.c (entries in the order of insertion, an index of their
// positions, compaction when the array is full), as a reference-counted cell:
// each write first copies it unless this is its only reference, and reading
// a missing key traps, as `m[k]` does. The keys are integers, which own
// nothing.
#include "../myla_rt.h"

#define LIVE 1000

typedef struct { int64_t key, value; int dead; } Entry;
typedef struct {
    int64_t rc;
    Entry *entries;
    int64_t used, live, cap;
    int64_t *index;  // 2 * cap slots: -1 empty, -2 a tombstone, else a position
} Map;

static int64_t key(int64_t i) { return i * 2654435761 % 4294967296; }

static uint64_t slot_of(int64_t k, int64_t mask) {
    uint64_t h = (uint64_t)k * 11400714819323198485ull;
    return (h ^ (h >> 32)) & (uint64_t)mask;
}

static Map *map_new(int64_t cap) {
    Map *m = myla_alloc(sizeof *m);
    m->rc = 1;
    m->entries = myla_alloc(sizeof(Entry) * (size_t)cap);
    m->index = myla_alloc(sizeof(int64_t) * 2 * (size_t)cap);
    for (int64_t i = 0; i < 2 * cap; i++) m->index[i] = -1;
    m->used = m->live = 0;
    m->cap = cap;
    return m;
}

static void map_release(Map *m) {
    if (--m->rc > 0) return;
    free(m->entries);
    free(m->index);
    free(m);
}

static int64_t find(const Map *m, int64_t k) {
    int64_t mask = 2 * m->cap - 1;
    for (uint64_t i = slot_of(k, mask);; i = (i + 1) & (uint64_t)mask) {
        int64_t at = m->index[i];
        if (at == -1 || (at >= 0 && m->entries[at].key == k)) return (int64_t)i;
    }
}

// The live entries in a new cell of `cap`, in order and re-indexed.
static Map *rebuilt(const Map *m, int64_t cap) {
    Map *fresh = map_new(cap);
    for (int64_t i = 0; i < m->used; i++) {
        if (m->entries[i].dead) continue;
        fresh->index[find(fresh, m->entries[i].key)] = fresh->used;
        fresh->entries[fresh->used++] = m->entries[i];
    }
    fresh->live = fresh->used;
    return fresh;
}

// The map made unique before a write (copy-on-write).
static void unique(Map **mp) {
    if ((*mp)->rc == 1) return;
    Map *copy = rebuilt(*mp, (*mp)->cap);
    map_release(*mp);
    *mp = copy;
}

static void map_set(Map **mp, int64_t k, int64_t v) {
    unique(mp);
    Map *m = *mp;
    int64_t i = find(m, k);
    if (m->index[i] >= 0) {
        m->entries[m->index[i]].value = v;
        return;
    }
    if (m->used == m->cap) {
        Map *fresh = rebuilt(m, m->live * 2 >= m->cap ? m->cap * 2 : m->cap);
        map_release(m);
        *mp = m = fresh;
        i = find(m, k);
    }
    m->index[i] = m->used;
    m->entries[m->used++] = (Entry){k, v, 0};
    m->live++;
}

static int map_contains(const Map *m, int64_t k) { return m->index[find(m, k)] >= 0; }

static int64_t map_get(const Map *m, int64_t k) {
    int64_t at = m->index[find(m, k)];
    if (at < 0) myla_trap("key not found");
    return m->entries[at].value;
}

static void map_remove(Map **mp, int64_t k) {
    unique(mp);
    Map *m = *mp;
    int64_t i = find(m, k);
    if (m->index[i] < 0) return;
    m->entries[m->index[i]].dead = 1;
    m->index[i] = -2;
    m->live--;
}

int main(int argc, char **argv) {
    int64_t n = myla_size(argc, argv, 32000);
    Map *m = map_new(8);
    for (int64_t i = 0; i < n; i++) map_set(&m, key(i), 2 * i);
    int64_t sum = 0;
    for (int64_t start = 0; start < 2; start++) {
        for (int64_t j = start; j < n; j += 2) {
            sum += map_get(m, key(j));
            map_remove(&m, key(j));
        }
    }
    printf("%lld\n%lld\n", (long long)m->live, (long long)sum);
    map_release(m);

    m = map_new(8);
    int64_t found = 0;
    for (int64_t s = 0; s < 4 * n; s++) {
        map_set(&m, key(s), s);
        if (s >= LIVE) map_remove(&m, key(s - LIVE));
        if (s % 97 == 0 && s >= 500) map_set(&m, key(s - 500), -s);
        if (s % 89 == 0 && s >= 300) {
            int64_t k = key(s - 300);
            map_remove(&m, k);
            map_set(&m, k, s);
        }
        if (map_contains(m, key(s - 700))) found++;
    }
    int64_t total = 0, place = 1;
    for (int64_t i = 0; i < m->used; i++) {
        if (m->entries[i].dead) continue;
        total += place * (m->entries[i].key - map_get(m, m->entries[i].key));
        place++;
    }
    printf("%lld\n%lld\n%lld\n", (long long)m->live, (long long)found, (long long)total);
    map_release(m);
    return 0;
}
