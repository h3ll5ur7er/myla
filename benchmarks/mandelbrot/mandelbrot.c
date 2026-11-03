// Benchmark (MYLA-242): points of the Mandelbrot set, idiomatic C.
// The same operations in the same order as the Myla program, so the floats
// are bit-identical.
#include <stdio.h>
#include <stdlib.h>

static int inside(double cr, double ci) {
    double zr = 0.0, zi = 0.0;
    for (int i = 0; i < 50; i++) {
        double tr = zr * zr - zi * zi + cr;
        zi = 2.0 * zr * zi + ci;
        zr = tr;
        if (zr * zr + zi * zi > 4.0) return 0;
    }
    return 1;
}

static int count(int n) {
    int total = 0;
    for (int y = 0; y < n; y++) {
        double ci = 3.0 * (double)y / (double)n - 1.5;
        for (int x = 0; x < n; x++) {
            double cr = 3.0 * (double)x / (double)n - 2.0;
            if (inside(cr, ci)) total++;
        }
    }
    return total;
}

int main(int argc, char **argv) {
    printf("%d\n", count(argc > 1 ? atoi(argv[1]) : 1000));
    return 0;
}
