// Benchmark (MYLA-242): the sieve with Myla's semantics: a growable,
// reference-counted list of flags built by pushes, every index checked, every
// write checking that the list is held once (copy-on-write).
#include <stdbool.h>
#include "../myla_rt.h"

MYLA_LIST(BoolList, bool)

static int32_t count_primes(int32_t n) {
    BoolList *composite = BoolList_new();
    for (int32_t i = 0; i < n; i++) BoolList_push(&composite, false);
    int32_t count = 0;
    for (int32_t i = 2; i < n; i++) {
        if (!BoolList_get(composite, i)) {
            count++;
            if (i <= myla_div(n - 1, i))
                for (int32_t j = i * i; j < n; j += i) BoolList_set(&composite, j, true);
        }
    }
    BoolList_release(composite);
    return count;
}

int main(int argc, char **argv) {
    printf("%d\n", count_primes(myla_size(argc, argv, 10000000)));
    return 0;
}
