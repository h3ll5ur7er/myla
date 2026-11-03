// Benchmark (MYLA-242): Game of Life with Myla's semantics: a grid is a
// reference-counted list of reference-counted rows, each built by pushes,
// every index checked; a new grid each generation, the old one released.
// Rows are read through borrows (the grid isn't changed meanwhile).
#include <stdbool.h>
#include "../myla_rt.h"

MYLA_LIST(Row, bool)
MYLA_LIST(Grid, Row *)

static void grid_release(Grid *g) {
    if (g->rc == 1)
        for (int64_t i = 0; i < g->len; i++) Row_release(g->items[i]);
    Grid_release(g);
}

static Grid *step(const Grid *grid, int32_t n) {
    Grid *next = Grid_new();
    for (int32_t y = 0; y < n; y++) {
        const Row *up = Grid_get(grid, (y + n - 1) % n);
        const Row *mid = Grid_get(grid, y);
        const Row *down = Grid_get(grid, (y + 1) % n);
        Row *row = Row_new();
        for (int32_t x = 0; x < n; x++) {
            int32_t l = (x + n - 1) % n, r = (x + 1) % n;
            int32_t c = 0;
            if (Row_get(up, l)) c++;
            if (Row_get(up, x)) c++;
            if (Row_get(up, r)) c++;
            if (Row_get(mid, l)) c++;
            if (Row_get(mid, r)) c++;
            if (Row_get(down, l)) c++;
            if (Row_get(down, x)) c++;
            if (Row_get(down, r)) c++;
            Row_push(&row, c == 3 || (Row_get(mid, x) && c == 2));
        }
        Grid_push(&next, row);
    }
    return next;
}

int main(int argc, char **argv) {
    int32_t n = myla_size(argc, argv, 300);
    int64_t state = 42;
    Grid *grid = Grid_new();
    for (int32_t y = 0; y < n; y++) {
        Row *row = Row_new();
        for (int32_t x = 0; x < n; x++) {
            state = (state * 1103515245 + 12345) % 2147483648;
            Row_push(&row, (state >> 16) % 3 == 0);
        }
        Grid_push(&grid, row);
    }
    for (int32_t g = 0; g < 50; g++) {
        Grid *next = step(grid, n);
        grid_release(grid);
        grid = next;
    }
    int32_t total = 0;
    for (int64_t y = 0; y < grid->len; y++) {
        const Row *row = Grid_get(grid, y);
        for (int64_t x = 0; x < row->len; x++) if (Row_get(row, x)) total++;
    }
    printf("%d\n", total);
    grid_release(grid);
    return 0;
}
