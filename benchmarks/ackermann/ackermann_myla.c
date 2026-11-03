// Benchmark (MYLA-242): Ackermann with Myla's semantics. They add nothing
// here: no heap values, and int32 arithmetic wraps (-fwrapv).
#include "../myla_rt.h"

static int32_t ack(int32_t m, int32_t n) {
    if (m == 0) return n + 1;
    if (n == 0) return ack(m - 1, 1);
    return ack(m - 1, ack(m, n - 1));
}

int main(int argc, char **argv) {
    printf("%d\n", ack(3, myla_size(argc, argv, 10)));
    return 0;
}
