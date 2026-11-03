// Benchmark (MYLA-242): fannkuch-redux with Myla's semantics: the lists are
// reference-counted, every index is checked, and `perm = perm1` shares the
// list until its first write copies it (copy-on-write); perm is dropped
// after its last use.
#include "../myla_rt.h"

MYLA_LIST(IntList, int32_t)

int main(int argc, char **argv) {
    int32_t n = myla_size(argc, argv, 10);
    IntList *perm1 = IntList_new(), *count = IntList_new();
    for (int32_t i = 0; i < n; i++) { IntList_push(&perm1, i); IntList_push(&count, 0); }
    int32_t max_flips = 0, checksum = 0, perm_count = 0, r = n;
    for (;;) {
        while (r != 1) { IntList_set(&count, r - 1, r); r--; }
        IntList *perm = perm1;
        IntList_retain(perm);
        int32_t flips = 0;
        for (int32_t k = IntList_get(perm, 0); k != 0; k = IntList_get(perm, 0)) {
            for (int32_t i = 0, j = k; i < j; i++, j--) {
                int32_t t = IntList_get(perm, i);
                IntList_set(&perm, i, IntList_get(perm, j));
                IntList_set(&perm, j, t);
            }
            flips++;
        }
        IntList_release(perm);
        if (flips > max_flips) max_flips = flips;
        if (perm_count % 2 == 0) checksum += flips; else checksum -= flips;
        for (;;) {
            if (r == n) {
                printf("%d\n%d\n", checksum, max_flips);
                IntList_release(perm1);
                IntList_release(count);
                return 0;
            }
            int32_t first = IntList_get(perm1, 0);
            for (int32_t i = 0; i < r; i++) IntList_set(&perm1, i, IntList_get(perm1, i + 1));
            IntList_set(&perm1, r, first);
            IntList_set(&count, r, IntList_get(count, r) - 1);
            if (IntList_get(count, r) > 0) break;
            r++;
        }
        perm_count++;
    }
}
