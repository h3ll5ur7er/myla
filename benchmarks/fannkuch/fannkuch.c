// Benchmark (MYLA-242): fannkuch-redux, idiomatic C: fixed arrays, the
// permutation copied with memcpy.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 10;
    int perm1[32], perm[32], count[32];
    for (int i = 0; i < n; i++) { perm1[i] = i; count[i] = 0; }
    int max_flips = 0, checksum = 0, perm_count = 0, r = n;
    for (;;) {
        while (r != 1) { count[r - 1] = r; r--; }
        memcpy(perm, perm1, sizeof(int) * (size_t)n);
        int flips = 0;
        for (int k = perm[0]; k != 0; k = perm[0]) {
            for (int i = 0, j = k; i < j; i++, j--) { int t = perm[i]; perm[i] = perm[j]; perm[j] = t; }
            flips++;
        }
        if (flips > max_flips) max_flips = flips;
        checksum += perm_count % 2 == 0 ? flips : -flips;
        for (;;) {
            if (r == n) { printf("%d\n%d\n", checksum, max_flips); return 0; }
            int first = perm1[0];
            for (int i = 0; i < r; i++) perm1[i] = perm1[i + 1];
            perm1[r] = first;
            if (--count[r] > 0) break;
            r++;
        }
        perm_count++;
    }
}
