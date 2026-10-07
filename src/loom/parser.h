/* parser.h — AST for Loom */
#ifndef LOOM_PARSER_H
#define LOOM_PARSER_H

#include "lexer.h"

typedef enum {
    /* statements */
    S_LET,        /* LET/DIM name [= expr] [: type] */
    S_ASSIGN,     /* target = expr  (target: ident | ident[idx] | obj.field) */
    S_EXPR,       /* bare expression statement (call etc.) */
    S_CONSOLE,    /* console(...) / console ... */
    S_INPUT,      /* INPUT [var] */
    S_IF,         /* IF cond THEN block [ELSEIF ...] [ELSE ...] ENDIF */
    S_FOR,        /* FOR v = a TO b [STEP s] block NEXT   |  FOR v IN expr block NEXT */
    S_WHILE,      /* WHILE cond block WHILEEND */
    S_DOWHILE,    /* DO block UNTIL cond */
    S_EXIT,       /* EXIT (loop) */
    S_GOTO,       /* GOTO label */
    S_GOSUB,      /* GOSUB label */
    S_RETURN,     /* RETURN [expr] */
    S_CALL,       /* CALL name(args) */
    S_DEF,        /* DEF name(params) block ENDDEF */
    S_CLASS,      /* CLASS Name [extends X] members ENDCLASS */
    S_LAMBDA_DEF, /* name = LAMBDA(params) expr END */
    S_IMPORT,     /* IMPORT "lib" */
    S_LABEL,      /* identifier ':' at line start */
    S_TRY,        /* TRY block CATCH [e] block [FINALLY block] END */
    S_SWITCH,     /* SWITCH expr CASE v: block ... DEFAULT: block END */
    S_BREAK,
    S_THROW,      /* THROW expr */
    S_BLOCK,      /* sequence of statements */
    S_REFLECT,    /* REFLECT expr */
    S_NEW_STMT,
    /* expressions */
    E_INT, E_DOUBLE, E_STR, E_BOOLK, E_NULLK, E_IDENT,
    E_BIN, E_UN, E_NOT, E_CALL, E_INDEX, E_FIELD, E_LAMBDA,
    E_ARRAYLIT, E_NEW, E_GROUPED,
} NodeType;

/* binary/unary operator codes */
typedef enum {
    OP_ADD, OP_SUB, OP_MUL, OP_DIV, OP_MOD, OP_POW,
    OP_EQ, OP_NEQ, OP_LT, OP_GT, OP_LE, OP_GE,
    OP_AND, OP_OR, OP_IS,
    OP_BAND, OP_BOR, OP_BXOR, OP_SHL, OP_SHR,
    OP_NEG, OP_POS, OP_LNOT,
} OpKind;

typedef struct Node Node;

typedef struct {
    char *name;
    Node *init;        /* may be NULL */
    int type_ann;      /* declared type keyword token or T_EOF_TOK */
} LetDecl;

struct Node {
    NodeType type;
    int line;
    union {
        struct { long long i; } ival;
        struct { double d; } dval;
        struct { char *s; } sval;
        struct { char *name; } ident;          /* E_IDENT, S_LABEL */
        struct { OpKind op; Node *a, *b; } bin; /* also unary via op + a */
        struct { Node *arg; } un;
        struct { Node *callee; Node **args; int nargs; } call;
        struct { Node *obj; Node *idx; } index;
        struct { Node *target; char *field; } field;
        struct { LetDecl decl; } let;           /* S_LET */
        struct { Node *target; Node *value; } assign;
        struct { Node *cond; Node *then; Node *els; } iff;   /* els may be S_IF chain */
        struct { char *var; Node *from,*to,*step; Node *body;
                 char *invar; Node *iterable; } foor;
        struct { Node *cond; Node *body; } whl;
        struct { Node *body; Node *cond; } dowhile;
        struct { Node **stmts; int n; } block;
        struct { char *name; char **params; int np; Node *body; } def;
        struct { char *name; char *parent; Node *body; } cls;
        struct { char *label; } goto_;
        struct { Node *value; } retv;            /* value may be NULL */
        struct { char *mod; } imp;
        struct { Node *tryb; char *errvar; Node *catchb; Node *finallyb; } trystmt;
        struct { Node *subj; Node **cases; Node **bodies; int ncase; Node *dflt; } swtch;
        struct { Node *fn; Node **args; int nargs; } new_;
        struct { char **params; int np; Node *body; int is_expr; } lam;
        struct { Node **items; int n; } arrlit;
        struct { Node *x; } reflect;
        struct { Node *single; } solo;           /* console/input/throw/exit single arg */
    } u;
};

Node *parse_program(Token *toks, int n);
void node_free(Node *n);

#endif /* LOOM_PARSER_H */
