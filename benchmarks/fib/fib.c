// Benchmark (MYLA-242): the naive recursive Fibonacci number, idiomatic C.
#include <stdio.h>
#include <stdlib.h>

static int fib(int n) {
    if (n < 2) return n;
    return fib(n - 1) + fib(n - 2);
}

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 32;
    printf("%d\n", fib(n));
    return 0;
}
