// Benchmark (MYLA-975): the FFT of fft_split.my and fft_complex.my in C#,
// operation for operation, with the base library only (no System.Numerics,
// no native code).
//
//   dotnet out/Program.dll split|complex [points rounds]
//
// `split` keeps two arrays of doubles, `complex` one array of a struct with
// operators.
using System.Diagnostics;
using System.Globalization;

bool split = args[0] == "split";
if (args.Length == 3)
{
    Run(split, int.Parse(args[1]), int.Parse(args[2]));
}
else
{
    Run(split, 4096, 10000);
    Run(split, 1 << 20, 10);
}

// Times `rounds` round trips of `n` points, without the table and the input.
static void Run(bool split, int n, int rounds)
{
    long checksum = 0, error;
    Stopwatch watch;
    if (split)
    {
        var plan = SplitSignal.Plan(n);
        var input = SplitSignal.Noise(n);
        var x = SplitSignal.Noise(n);
        watch = Stopwatch.StartNew();
        for (int r = 0; r < rounds; r++)
        {
            x.Transform(plan, false);
            if (r == 0) checksum = (long)(x.Weight() * 1000.0);
            x.Transform(plan, true);
        }
        error = (long)(x.Distance(input) * 1e15);
    }
    else
    {
        var w = ComplexSignal.Plan(n);
        var input = ComplexSignal.Noise(n);
        var x = ComplexSignal.Noise(n);
        watch = Stopwatch.StartNew();
        for (int r = 0; r < rounds; r++)
        {
            ComplexSignal.Transform(x, w, false);
            if (r == 0) checksum = (long)(ComplexSignal.Weight(x) * 1000.0);
            ComplexSignal.Transform(x, w, true);
        }
        error = (long)(ComplexSignal.Distance(x, input) * 1e15);
    }
    double secs = watch.Elapsed.TotalSeconds;
    Console.WriteLine(string.Create(CultureInfo.InvariantCulture, $"fft-{n} {checksum} {error} {rounds} {secs:F6}"));
}

static class Lcg
{
    public const int Seed = 42, Im = 139968, Ia = 3877, Ic = 29573;

    public static int Next(int seed) => (seed * Ia + Ic) % Im;
}

static class Roots
{
    // cos and sin of 2π/m for m = 4, 8, … n, each from the one before.
    public static (List<double> Cos, List<double> Sin) Of(int n)
    {
        var cs = new List<double> { 0.0 };
        var sn = new List<double> { 1.0 };
        for (int m = 4; m < n; m *= 2)
        {
            double half = Math.Sqrt((1.0 + cs[^1]) / 2.0);
            sn.Add(sn[^1] / (2.0 * half));
            cs.Add(half);
        }
        return (cs, sn);
    }
}

sealed class SplitSignal(double[] re, double[] im)
{
    readonly double[] re = re, im = im;

    public static SplitSignal Plan(int n)
    {
        var (cs, sn) = Roots.Of(n);
        var wr = new double[Math.Max(n / 2, 1)];
        var wi = new double[wr.Length];
        wr[0] = 1.0;
        int level = cs.Count - 1;
        for (int h = 1; h < n / 2; h *= 2, level--)
        {
            double c = cs[level], s = sn[level];
            for (int k = 0; k < h; k++)
            {
                wr[h + k] = wr[k] * c + wi[k] * s;
                wi[h + k] = wi[k] * c - wr[k] * s;
            }
        }
        return new SplitSignal(wr, wi);
    }

    public static SplitSignal Noise(int n)
    {
        var re = new double[n];
        var im = new double[n];
        int seed = Lcg.Seed;
        for (int i = 0; i < n; i++)
        {
            seed = Lcg.Next(seed);
            re[i] = (double)seed / Lcg.Im - 0.5;
            seed = Lcg.Next(seed);
            im[i] = (double)seed / Lcg.Im - 0.5;
        }
        return new SplitSignal(re, im);
    }

    // The transform in place; `inverse` also divides by the length.
    public void Transform(SplitSignal plan, bool inverse)
    {
        int n = re.Length;
        for (int i = 1, j = 0; i < n; i++)
        {
            int bit = n >> 1;
            for (; (j & bit) != 0; bit >>= 1) j ^= bit;
            j ^= bit;
            if (i < j)
            {
                (re[i], re[j]) = (re[j], re[i]);
                (im[i], im[j]) = (im[j], im[i]);
            }
        }
        double sign = inverse ? -1.0 : 1.0;
        for (int len = 2; len <= n; len *= 2)
        {
            int half = len / 2, step = n / len;
            for (int start = 0; start < n; start += len)
            {
                for (int k = 0; k < half; k++)
                {
                    double wr = plan.re[k * step];
                    double wi = sign * plan.im[k * step];
                    int a = start + k, b = a + half;
                    double vr = re[b] * wr - im[b] * wi;
                    double vi = re[b] * wi + im[b] * wr;
                    double ur = re[a], ui = im[a];
                    re[a] = ur + vr;
                    im[a] = ui + vi;
                    re[b] = ur - vr;
                    im[b] = ui - vi;
                }
            }
        }
        if (inverse)
        {
            double scale = 1.0 / n;
            for (int i = 0; i < n; i++)
            {
                re[i] *= scale;
                im[i] *= scale;
            }
        }
    }

    public double Weight()
    {
        double sum = 0.0;
        for (int i = 0; i < re.Length; i++) sum += Math.Abs(re[i]) + Math.Abs(im[i]);
        return sum;
    }

    public double Distance(SplitSignal other)
    {
        double worst = 0.0;
        for (int i = 0; i < re.Length; i++)
        {
            double d = Math.Abs(re[i] - other.re[i]) + Math.Abs(im[i] - other.im[i]);
            if (d > worst) worst = d;
        }
        return worst;
    }
}

readonly record struct Complex(double Re, double Im)
{
    public static Complex operator +(Complex a, Complex b) => new(a.Re + b.Re, a.Im + b.Im);
    public static Complex operator -(Complex a, Complex b) => new(a.Re - b.Re, a.Im - b.Im);
    public static Complex operator *(Complex a, Complex b) => new(a.Re * b.Re - a.Im * b.Im, a.Re * b.Im + a.Im * b.Re);

    // The number with its imaginary part times `sign`: itself or its conjugate.
    public Complex Turned(double sign) => new(Re, sign * Im);
    public Complex Scaled(double by) => new(Re * by, Im * by);
    public double Size => Math.Abs(Re) + Math.Abs(Im);
}

static class ComplexSignal
{
    public static Complex[] Plan(int n)
    {
        var (cs, sn) = Roots.Of(n);
        var w = new Complex[Math.Max(n / 2, 1)];
        w[0] = new Complex(1.0, 0.0);
        int level = cs.Count - 1;
        for (int h = 1; h < n / 2; h *= 2, level--)
        {
            var root = new Complex(cs[level], -sn[level]);
            for (int k = 0; k < h; k++)
            {
                w[h + k] = new Complex(w[k].Re * root.Re - w[k].Im * root.Im, w[k].Im * root.Re + w[k].Re * root.Im);
            }
        }
        return w;
    }

    public static Complex[] Noise(int n)
    {
        var x = new Complex[n];
        int seed = Lcg.Seed;
        for (int i = 0; i < n; i++)
        {
            seed = Lcg.Next(seed);
            double re = (double)seed / Lcg.Im - 0.5;
            seed = Lcg.Next(seed);
            x[i] = new Complex(re, (double)seed / Lcg.Im - 0.5);
        }
        return x;
    }

    // The transform in place; `inverse` also divides by the length.
    public static void Transform(Complex[] x, Complex[] w, bool inverse)
    {
        int n = x.Length;
        for (int i = 1, j = 0; i < n; i++)
        {
            int bit = n >> 1;
            for (; (j & bit) != 0; bit >>= 1) j ^= bit;
            j ^= bit;
            if (i < j) (x[i], x[j]) = (x[j], x[i]);
        }
        double sign = inverse ? -1.0 : 1.0;
        for (int len = 2; len <= n; len *= 2)
        {
            int half = len / 2, step = n / len;
            for (int start = 0; start < n; start += len)
            {
                for (int k = 0; k < half; k++)
                {
                    int a = start + k, b = a + half;
                    Complex v = x[b] * w[k * step].Turned(sign);
                    Complex u = x[a];
                    x[a] = u + v;
                    x[b] = u - v;
                }
            }
        }
        if (inverse)
        {
            double scale = 1.0 / n;
            for (int i = 0; i < n; i++) x[i] = x[i].Scaled(scale);
        }
    }

    public static double Weight(Complex[] x)
    {
        double sum = 0.0;
        foreach (var z in x) sum += z.Size;
        return sum;
    }

    public static double Distance(Complex[] x, Complex[] y)
    {
        double worst = 0.0;
        for (int i = 0; i < x.Length; i++)
        {
            double d = (x[i] - y[i]).Size;
            if (d > worst) worst = d;
        }
        return worst;
    }
}
