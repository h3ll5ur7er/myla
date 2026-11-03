// Benchmark (MYLA-242): fib with Myla's semantics. They add nothing here: no
// heap values, and int32 arithmetic wraps (-fwrapv).
#include "../myla_rt.h"

static int32_t fib(int32_t n) {
    if (n < 2) return n;
    return fib(n - 1) + fib(n - 2);
}

int main(int argc, char **argv) {
    printf("%d\n", fib(myla_size(argc, argv, 32)));
    return 0;
}
