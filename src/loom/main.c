/* main.c — Loom CLI: loom [file.loom] [-e "code"] [--tokens|--ast] */
#include "interp.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char *read_file(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = malloc((size_t)sz + 1);
    size_t got = fread(buf, 1, (size_t)sz, f);
    buf[got] = 0;
    fclose(f);
    return buf;
}

int main(int argc, char **argv) {
    const char *src = NULL;
    int dump_tokens = 0, dump_ast = 0;
    char *heap_src = NULL;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-e") && i + 1 < argc) { src = argv[++i]; }
        else if (!strcmp(argv[i], "--tokens")) dump_tokens = 1;
        else if (!strcmp(argv[i], "--ast"))    dump_ast = 1;
        else if (!strcmp(argv[i], "--version") || !strcmp(argv[i], "-V")) {
            printf("loom 0.1.0 (bootstrap)\n");
            return 0;
        }
        else heap_src = read_file(argv[i]);
    }
    if (!src) {
        if (!heap_src) {
            fprintf(stderr, "usage: loom <file.loom> | -e \"code\" [--tokens] [--ast]\n");
            return 2;
        }
        src = heap_src;
    }

    int n = 0;
    Token *toks = lex(src, &n);
    if (dump_tokens) {
        for (int i = 0; i < n; i++)
            printf("%d:%d [%d] %s\n", toks[i].line, toks[i].col,
                   (int)toks[i].type, toks[i].text ? toks[i].text : "");
        return 0;
    }
    Node *prog = parse_program(toks, n);
    if (dump_ast) {
        printf("(program stmts=%d)\n", prog->u.block.n);
        return 0;
    }

    Interp ip;
    interp_init(&ip);
    interp_run(&ip, prog);
    return 0;
}
