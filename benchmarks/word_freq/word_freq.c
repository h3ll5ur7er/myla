// Benchmark (MYLA-242): word frequencies, idiomatic C: the text in one
// buffer, an open-addressing hash table whose keys point into it.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define VOCABULARY 5000

typedef struct { const char *key; int len; int count; } Slot;

static int word(int64_t i, char *out) {
    int n = 0;
    for (int64_t k = i + 1; k > 0; k /= 26) out[n++] = (char)(97 + k % 26);
    return n;
}

static uint64_t hash(const char *s, int len) {
    uint64_t h = 1469598103934665603ull;
    for (int i = 0; i < len; i++) h = (h ^ (unsigned char)s[i]) * 1099511628211ull;
    return h;
}

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 2000000;
    size_t cap = 16, len = 0;
    char *text = malloc(cap);
    int64_t state = 7;
    for (int i = 0; i < n; i++) {
        state = (state * 1103515245 + 12345) % 2147483648;
        int64_t a = (state >> 8) % VOCABULARY;
        state = (state * 1103515245 + 12345) % 2147483648;
        int64_t b = (state >> 8) % VOCABULARY;
        char w[16];
        int wl = word(a * b / VOCABULARY, w);
        while (len + (size_t)wl + 1 > cap) { cap *= 2; text = realloc(text, cap); }
        if (i > 0) text[len++] = ' ';
        memcpy(text + len, w, (size_t)wl);
        len += (size_t)wl;
    }
    size_t slots = 1024, used = 0;
    Slot *table = calloc(slots, sizeof *table);
    size_t start = 0;
    for (size_t i = 0; i <= len; i++) {
        if (i == len || text[i] == ' ') {
            if (i > start) {
                const char *k = text + start;
                int kl = (int)(i - start);
                size_t at = hash(k, kl) & (slots - 1);
                while (table[at].key && (table[at].len != kl || memcmp(table[at].key, k, (size_t)kl)))
                    at = (at + 1) & (slots - 1);
                if (table[at].key) {
                    table[at].count++;
                } else {
                    table[at] = (Slot){k, kl, 1};
                    if (++used * 2 > slots) {          // grow at half full
                        Slot *old = table;
                        size_t old_slots = slots;
                        slots *= 2;
                        table = calloc(slots, sizeof *table);
                        for (size_t j = 0; j < old_slots; j++) {
                            if (!old[j].key) continue;
                            size_t to = hash(old[j].key, old[j].len) & (slots - 1);
                            while (table[to].key) to = (to + 1) & (slots - 1);
                            table[to] = old[j];
                        }
                        free(old);
                    }
                }
            }
            start = i + 1;
        }
    }
    int most = 0;
    long long squares = 0;
    for (size_t j = 0; j < slots; j++) {
        if (!table[j].key) continue;
        if (table[j].count > most) most = table[j].count;
        squares += (long long)table[j].count * table[j].count;
    }
    printf("%zu\n%d\n%lld\n", used, most, squares);
    free(table);
    free(text);
    return 0;
}
