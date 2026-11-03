// Benchmark (MYLA-242): the sieve of Eratosthenes, idiomatic C.
#include <stdio.h>
#include <stdlib.h>

static int count_primes(int n) {
    unsigned char *composite = calloc(n > 0 ? (size_t)n : 1, 1);
    int count = 0;
    for (int i = 2; i < n; i++) {
        if (!composite[i]) {
            count++;
            if (i <= (n - 1) / i)
                for (int j = i * i; j < n; j += i) composite[j] = 1;
        }
    }
    free(composite);
    return count;
}

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 10000000;
    printf("%d\n", count_primes(n));
    return 0;
}
