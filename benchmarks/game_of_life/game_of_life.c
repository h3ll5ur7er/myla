// Benchmark (MYLA-242): Game of Life, idiomatic C: two flat byte grids,
// swapped each generation.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 300;
    unsigned char *grid = malloc((size_t)n * n + 1), *next = malloc((size_t)n * n + 1);
    int64_t state = 42;
    for (int i = 0; i < n * n; i++) {
        state = (state * 1103515245 + 12345) % 2147483648;
        grid[i] = (state >> 16) % 3 == 0;
    }
    for (int g = 0; g < 50; g++) {
        for (int y = 0; y < n; y++) {
            const unsigned char *up = grid + (size_t)((y + n - 1) % n) * n;
            const unsigned char *mid = grid + (size_t)y * n;
            const unsigned char *down = grid + (size_t)((y + 1) % n) * n;
            for (int x = 0; x < n; x++) {
                int l = (x + n - 1) % n, r = (x + 1) % n;
                int c = up[l] + up[x] + up[r] + mid[l] + mid[r] + down[l] + down[x] + down[r];
                next[(size_t)y * n + x] = c == 3 || (mid[x] && c == 2);
            }
        }
        unsigned char *t = grid; grid = next; next = t;
    }
    int total = 0;
    for (int i = 0; i < n * n; i++) total += grid[i];
    printf("%d\n", total);
    free(grid);
    free(next);
    return 0;
}
