// Benchmark (MYLA-242): word frequencies with Myla's semantics: each word is
// made as a new string (by a builder, as `word` and the split make it), the
// map owns its keys (a new word is kept, a known one released), and each
// byte read from the text is checked.
#include "../myla_rt.h"

#define VOCABULARY 5000

typedef struct { MylaStr *key; int32_t count; } Slot;

static MylaStr *word(int64_t i) {
    MylaBuilder b = {0, 0, NULL};
    for (int64_t k = i + 1; k > 0; k = k / 26) {
        char c = (char)(97 + k % 26);
        mb_append(&b, &c, 1);
    }
    MylaStr *s = mb_build(&b);
    free(b.bytes);
    return s;
}

static uint64_t hash(const MylaStr *s) {
    uint64_t h = 1469598103934665603ull;
    for (int64_t i = 0; i < s->len; i++) h = (h ^ (unsigned char)s->bytes[i]) * 1099511628211ull;
    return h;
}

static MylaStr *text(int32_t n) {
    MylaBuilder b = {0, 0, NULL};
    int64_t state = 7;
    for (int32_t i = 0; i < n; i++) {
        state = (state * 1103515245 + 12345) % 2147483648;
        int64_t a = (state >> 8) % VOCABULARY;
        state = (state * 1103515245 + 12345) % 2147483648;
        int64_t c = (state >> 8) % VOCABULARY;
        if (i > 0) mb_append(&b, " ", 1);
        MylaStr *w = word(a * c / VOCABULARY);
        mb_append(&b, w->bytes, w->len);
        mstr_release(w);
    }
    MylaStr *s = mb_build(&b);
    free(b.bytes);
    return s;
}

int main(int argc, char **argv) {
    MylaStr *s = text(myla_size(argc, argv, 2000000));
    size_t slots = 1024, used = 0;
    Slot *table = calloc(slots, sizeof *table);
    int64_t start = 0;
    for (int64_t i = 0; i <= s->len; i++) {
        if (i == s->len || mstr_at(s, i) == ' ') {
            if (i > start) {
                MylaStr *w = mstr_new(s->bytes + start, i - start);
                size_t at = hash(w) & (slots - 1);
                while (table[at].key && (table[at].key->len != w->len || memcmp(table[at].key->bytes, w->bytes, (size_t)w->len)))
                    at = (at + 1) & (slots - 1);
                if (table[at].key) {
                    table[at].count = table[at].count + 1;
                    mstr_release(w);
                } else {
                    table[at] = (Slot){w, 1};
                    if (++used * 2 > slots) {
                        Slot *old = table;
                        size_t old_slots = slots;
                        slots *= 2;
                        table = calloc(slots, sizeof *table);
                        for (size_t j = 0; j < old_slots; j++) {
                            if (!old[j].key) continue;
                            size_t to = hash(old[j].key) & (slots - 1);
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
    int32_t most = 0;
    int64_t squares = 0;
    for (size_t j = 0; j < slots; j++) {
        if (!table[j].key) continue;
        if (table[j].count > most) most = table[j].count;
        squares += (int64_t)table[j].count * (int64_t)table[j].count;
        mstr_release(table[j].key);
    }
    printf("%zu\n%d\n%lld\n", used, most, (long long)squares);
    free(table);
    mstr_release(s);
    return 0;
}
