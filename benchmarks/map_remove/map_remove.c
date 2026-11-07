// Benchmark (MYLA-310): removing keys from a map, idiomatic C. A map that
// keeps its keys in the order of insertion, as Python's dict does: the
// entries in an array in that order, a removed one marked dead, and an
// open-addressing index of their positions (-1 empty, -2 a removed entry's
// tombstone). The entries are compacted when the array is full.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define LIVE 1000

typedef struct { int64_t key, value; int dead; } Entry;
typedef struct {
    Entry *entries;
    int64_t used, live, cap;  // entries used, of them live, the array's size
    int64_t *index;           // 2 * cap slots
} Map;

static int64_t key(int64_t i) { return i * 2654435761 % 4294967296; }

static uint64_t slot_of(int64_t k, int64_t mask) {
    uint64_t h = (uint64_t)k * 11400714819323198485ull;
    return (h ^ (h >> 32)) & (uint64_t)mask;
}

static void map_init(Map *m, int64_t cap) {
    m->entries = malloc(sizeof(Entry) * (size_t)cap);
    m->index = malloc(sizeof(int64_t) * 2 * (size_t)cap);
    for (int64_t i = 0; i < 2 * cap; i++) m->index[i] = -1;
    m->used = m->live = 0;
    m->cap = cap;
}

// The index slot of `k`: where it is, or the empty slot that ends its probe.
static int64_t find(const Map *m, int64_t k) {
    int64_t mask = 2 * m->cap - 1;
    for (uint64_t i = slot_of(k, mask);; i = (i + 1) & (uint64_t)mask) {
        int64_t at = m->index[i];
        if (at == -1 || (at >= 0 && m->entries[at].key == k)) return (int64_t)i;
    }
}

// The live entries moved to the front of an array of `cap`, re-indexed.
static void rebuild(Map *m, int64_t cap) {
    Map fresh;
    map_init(&fresh, cap);
    for (int64_t i = 0; i < m->used; i++) {
        if (m->entries[i].dead) continue;
        fresh.index[find(&fresh, m->entries[i].key)] = fresh.used;
        fresh.entries[fresh.used++] = m->entries[i];
    }
    fresh.live = fresh.used;
    free(m->entries);
    free(m->index);
    *m = fresh;
}

static void map_set(Map *m, int64_t k, int64_t v) {
    int64_t i = find(m, k);
    if (m->index[i] >= 0) {
        m->entries[m->index[i]].value = v;
        return;
    }
    if (m->used == m->cap) {
        rebuild(m, m->live * 2 >= m->cap ? m->cap * 2 : m->cap);
        i = find(m, k);
    }
    m->index[i] = m->used;
    m->entries[m->used++] = (Entry){k, v, 0};
    m->live++;
}

static int64_t *map_get(const Map *m, int64_t k) {
    int64_t at = m->index[find(m, k)];
    return at >= 0 ? &m->entries[at].value : NULL;
}

static void map_remove(Map *m, int64_t k) {
    int64_t i = find(m, k);
    if (m->index[i] < 0) return;
    m->entries[m->index[i]].dead = 1;
    m->index[i] = -2;
    m->live--;
}

int main(int argc, char **argv) {
    int64_t n = argc > 1 ? atoll(argv[1]) : 32000;
    Map m;
    map_init(&m, 8);
    for (int64_t i = 0; i < n; i++) map_set(&m, key(i), 2 * i);
    int64_t sum = 0;
    for (int64_t start = 0; start < 2; start++) {
        for (int64_t j = start; j < n; j += 2) {
            sum += *map_get(&m, key(j));
            map_remove(&m, key(j));
        }
    }
    printf("%lld\n%lld\n", (long long)m.live, (long long)sum);
    free(m.entries);
    free(m.index);

    map_init(&m, 8);
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
        if (map_get(&m, key(s - 700))) found++;
    }
    int64_t total = 0, place = 1;
    for (int64_t i = 0; i < m.used; i++) {
        if (m.entries[i].dead) continue;
        total += place * (m.entries[i].key - m.entries[i].value);
        place++;
    }
    printf("%lld\n%lld\n%lld\n", (long long)m.live, (long long)found, (long long)total);
    free(m.entries);
    free(m.index);
    return 0;
}
