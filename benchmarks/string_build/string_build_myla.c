// Benchmark (MYLA-242): string building with Myla's semantics: `format`, the
// concatenation and the f-string each make a new string (the f-string by
// formatting its holes and joining the pieces), released after use; each
// byte the checksum reads is checked.
#include "../myla_rt.h"

static MylaStr *records(int32_t n) {
    MylaBuilder b = {0, 0, NULL};
    MylaStr *k = mstr_new("k", 1), *eq = mstr_new("=", 1), *semi = mstr_new(";", 1);
    for (int32_t i = 0; i < n; i++) {
        MylaStr *num = mstr_int(i % 1000);
        MylaStr *key = mstr_concat(k, num);
        MylaStr *val = mstr_int(i * 7 % 10007);
        MylaStr *a = mstr_concat(key, eq);
        MylaStr *c = mstr_concat(a, val);
        MylaStr *rec = mstr_concat(c, semi);
        mb_append(&b, rec->bytes, rec->len);
        mstr_release(num);
        mstr_release(key);
        mstr_release(val);
        mstr_release(a);
        mstr_release(c);
        mstr_release(rec);
    }
    mstr_release(k);
    mstr_release(eq);
    mstr_release(semi);
    MylaStr *s = mb_build(&b);
    free(b.bytes);
    return s;
}

int main(int argc, char **argv) {
    MylaStr *s = records(myla_size(argc, argv, 2000000));
    int64_t h = 0;
    for (int64_t i = 0; i < s->len; i++) h = (h * 31 + (int64_t)mstr_at(s, i)) % 1000000007;
    printf("%lld\n%lld\n", (long long)s->len, (long long)h);
    mstr_release(s);
    return 0;
}
