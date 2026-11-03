// Benchmark (MYLA-242): n-body, Myla's semantics: the bodies' list has its indices checked; it is moved into each step and back, so it is never copied.
// The same operations in the same order as the Myla program, and the same
// correctly rounded square root, so the floats are bit-identical.
#include "../myla_rt.h"

typedef struct { double x, y, z, vx, vy, vz, mass; } Body;

#include <math.h>

#define PI 3.141592653589793
#define DAYS 365.24
#define N 5
static inline Body *at(Body *b, int i) {
    if ((unsigned)i >= N) myla_trap("index out of bounds");
    return &b[i];
}
#define AT(i) (*at(b, (i)))

static void planets(Body *b) {
    double sm = 4.0 * PI * PI;
    Body init[N] = {
        {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, sm},
        {4.84143144246472090, -1.16032004402742839, -0.103622044471123109,
         0.00166007664274403694 * DAYS, 0.00769901118419740425 * DAYS,
         -0.0000690460016972063023 * DAYS, 0.000954791938424326609 * sm},
        {8.34336671824457987, 4.12479856412430479, -0.403523417114321381,
         -0.00276742510726862411 * DAYS, 0.00499852801234917238 * DAYS,
         0.0000230417297573763929 * DAYS, 0.000285885980666130812 * sm},
        {12.8943695621391310, -15.1111514016986312, -0.223307578892655734,
         0.00296460137564761618 * DAYS, 0.00237847173959480950 * DAYS,
         -0.0000296589568540237556 * DAYS, 0.0000436624404335156298 * sm},
        {15.3796971148509165, -25.9193146099879641, 0.179258772950371181,
         0.00268067772490389322 * DAYS, 0.00162824170038242295 * DAYS,
         -0.0000951592254519715870 * DAYS, 0.0000515138902046611451 * sm},
    };
    for (int i = 0; i < N; i++) b[i] = init[i];
    double px = 0.0, py = 0.0, pz = 0.0;
    for (int i = 0; i < N; i++) {
        px += AT(i).vx * AT(i).mass;
        py += AT(i).vy * AT(i).mass;
        pz += AT(i).vz * AT(i).mass;
    }
    AT(0).vx = -px / sm;
    AT(0).vy = -py / sm;
    AT(0).vz = -pz / sm;
}

static double energy(Body *b) {
    double e = 0.0;
    for (int i = 0; i < N; i++) {
        e += 0.5 * AT(i).mass * (AT(i).vx * AT(i).vx + AT(i).vy * AT(i).vy + AT(i).vz * AT(i).vz);
        for (int j = i + 1; j < N; j++) {
            double dx = AT(i).x - AT(j).x, dy = AT(i).y - AT(j).y, dz = AT(i).z - AT(j).z;
            e -= AT(i).mass * AT(j).mass / sqrt(dx * dx + dy * dy + dz * dz);
        }
    }
    return e;
}

static void advance(Body *b, double dt) {
    for (int i = 0; i < N; i++) {
        for (int j = i + 1; j < N; j++) {
            double dx = AT(i).x - AT(j).x, dy = AT(i).y - AT(j).y, dz = AT(i).z - AT(j).z;
            double d2 = dx * dx + dy * dy + dz * dz;
            double mag = dt / (d2 * sqrt(d2));
            double mi = AT(i).mass, mj = AT(j).mass;
            AT(i).vx -= dx * mj * mag;
            AT(i).vy -= dy * mj * mag;
            AT(i).vz -= dz * mj * mag;
            AT(j).vx += dx * mi * mag;
            AT(j).vy += dy * mi * mag;
            AT(j).vz += dz * mi * mag;
        }
    }
    for (int i = 0; i < N; i++) {
        AT(i).x += dt * AT(i).vx;
        AT(i).y += dt * AT(i).vy;
        AT(i).z += dt * AT(i).vz;
    }
}

static long long simulate(int steps) {
    Body b[N];
    planets(b);
    for (int s = 0; s < steps; s++) advance(b, 0.01);
    return (long long)(energy(b) * 1000000000.0);
}

int main(int argc, char **argv) {
    printf("%lld\n%lld\n", simulate(0), simulate(myla_size(argc, argv, 1000000)));
    return 0;
}
