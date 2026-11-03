// Benchmark (MYLA-242): binary trees with Myla's semantics: a node of the
// recursive enum is a reference-counted cell (Leaf needs none); dropping the
// last reference to a node releases its children.
#include "../myla_rt.h"

typedef struct Node { int64_t rc; struct Node *left, *right; } Node;

static Node *node(Node *left, Node *right) {
    Node *n = myla_alloc(sizeof *n);
    n->rc = 1;
    n->left = left;
    n->right = right;
    return n;
}

static void release(Node *t) {
    while (t && --t->rc == 0) {
        release(t->left);
        Node *right = t->right;
        free(t);
        t = right;
    }
}

static Node *make(int32_t depth) {
    if (depth == 0) return node(NULL, NULL);
    Node *left = make(depth - 1);
    return node(left, make(depth - 1));
}

// a borrowed tree: no counts change
static int32_t check(const Node *t) {
    return t ? 1 + check(t->left) + check(t->right) : 0;
}

static int32_t nodes(int32_t depth) {
    Node *t = make(depth);
    int32_t c = check(t);
    release(t);
    return c;
}

int main(int argc, char **argv) {
    int32_t max_depth = myla_size(argc, argv, 16);
    if (max_depth < 6) max_depth = 6;
    int32_t stretch = max_depth + 1;
    printf("stretch tree of depth %d\t check: %d\n", stretch, nodes(stretch));
    Node *long_lived = make(max_depth);
    for (int32_t depth = 4; depth <= max_depth; depth += 2) {
        int32_t iterations = 1 << (max_depth - depth + 4);
        int32_t total = 0;
        for (int32_t i = 0; i < iterations; i++) total += nodes(depth);
        printf("%d\t trees of depth %d\t check: %d\n", iterations, depth, total);
    }
    printf("long lived tree of depth %d\t check: %d\n", max_depth, check(long_lived));
    release(long_lived);
    return 0;
}
