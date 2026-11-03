// Benchmark (MYLA-242): binary trees, idiomatic C: malloc and free, a leaf is
// NULL.
#include <stdio.h>
#include <stdlib.h>

typedef struct Node { struct Node *left, *right; } Node;

static Node *make(int depth) {
    Node *n = malloc(sizeof *n);
    if (depth == 0) {
        n->left = n->right = NULL;
    } else {
        n->left = make(depth - 1);
        n->right = make(depth - 1);
    }
    return n;
}

static int check(const Node *t) {
    return t ? 1 + check(t->left) + check(t->right) : 0;
}

static void drop(Node *t) {
    if (!t) return;
    drop(t->left);
    drop(t->right);
    free(t);
}

static int nodes(int depth) {
    Node *t = make(depth);
    int c = check(t);
    drop(t);
    return c;
}

int main(int argc, char **argv) {
    int max_depth = argc > 1 ? atoi(argv[1]) : 16;
    if (max_depth < 6) max_depth = 6;
    int stretch = max_depth + 1;
    printf("stretch tree of depth %d\t check: %d\n", stretch, nodes(stretch));
    Node *long_lived = make(max_depth);
    for (int depth = 4; depth <= max_depth; depth += 2) {
        int iterations = 1 << (max_depth - depth + 4);
        int total = 0;
        for (int i = 0; i < iterations; i++) total += nodes(depth);
        printf("%d\t trees of depth %d\t check: %d\n", iterations, depth, total);
    }
    printf("long lived tree of depth %d\t check: %d\n", max_depth, check(long_lived));
    drop(long_lived);
    return 0;
}
