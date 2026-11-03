// Benchmark (MYLA-242): string building, idiomatic C: one snprintf per
// record into a growing buffer.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 2000000;
    size_t cap = 16, len = 0;
    char *s = malloc(cap);
    for (int i = 0; i < n; i++) {
        char rec[32];
        int rl = snprintf(rec, sizeof rec, "k%d=%d;", i % 1000, i * 7 % 10007);
        while (len + (size_t)rl > cap) { cap *= 2; s = realloc(s, cap); }
        memcpy(s + len, rec, (size_t)rl);
        len += (size_t)rl;
    }
    int64_t h = 0;
    for (size_t i = 0; i < len; i++) h = (h * 31 + (unsigned char)s[i]) % 1000000007;
    printf("%zu\n%lld\n", len, (long long)h);
    free(s);
    return 0;
}
