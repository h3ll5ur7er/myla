// Benchmark (MYLA-242): the Ackermann function A(3, n), idiomatic C.
#include <stdio.h>
#include <stdlib.h>

static int ack(int m, int n) {
    if (m == 0) return n + 1;
    if (n == 0) return ack(m - 1, 1);
    return ack(m - 1, ack(m, n - 1));
}

int main(int argc, char **argv) {
    printf("%d\n", ack(3, argc > 1 ? atoi(argv[1]) : 10));
    return 0;
}
