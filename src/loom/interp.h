/* interp.h — tree-walking interpreter + runtime API for Loom */
#ifndef LOOM_INTERP_H
#define LOOM_INTERP_H

#include "parser.h"
#include <setjmp.h>

typedef struct Interp Interp;

typedef struct Env {
    struct Env *parent;
    char **names;
    Value *vals;
    int n, cap;
} Env;

typedef struct FuncDef {
    char *name;
    Node *body;
    char **params;
    int np;
    Env *closure;
    /* native functions: */
    Value (*native)(Interp *, Value *args, int nargs);
} FuncDef;

typedef struct ClassDef {
    char *name;
    Node *body;
    Env *env;              /* definitions inside class (methods) */
    char **fields; int nf; /* declared via DIM/LET at class top level */
} ClassDef;

/* bridge for value.h: Object.cls is really a ClassDef* */
#define LOOM_CLASS_CAST(cd)  ((ClassDesc*)(cd))
#define LOOM_CLASSDEF(v)     ((ClassDef*)(v))

typedef enum { SIG_NONE, SIG_EXIT_LOOP, SIG_RETURN, SIG_GOTO, SIG_GOSUB, SIG_THROW, SIG_BREAK } Signal;

typedef struct Interp {
    Env *globals;
    /* function & class tables */
    FuncDef **funcs; int nfuncs, fcap;
    ClassDef **classes; int nclasses, ccap;
    /* labels for GOTO/GOSUB: collected before run */
    struct { char *name; Node **stmt_index; } *labels; int nlabels, lcap;
    /* gosub return stack */
    int *gosub_stack; int ngosub, gcap;
    /* current program block being executed (for goto) */
    Node *main_block;
    int pc;                 /* program counter into main_block stmts (goto mode) */
    jmp_buf err_jmp;        /* for THROW/catch unwinding */
    Signal sig;             /* pending signal */
    Value retval;           /* pending return value */
    Value thrown;           /* thrown value */
    char *goto_target;
    int in_loop;            /* loop depth for EXIT/BREAK */
    /* file handles */
    struct FileH *files; int nfiles;
    int next_handle;
} Interp;

void interp_init(Interp *ip);
Value interp_run(Interp *ip, Node *prog);

/* environment helpers */
Env *env_new(Env *parent);
Value *env_get(Env *e, const char *name);
void env_set(Env *e, const char *name, Value v);   /* define in this env */
int  env_assign(Env *e, const char *name, Value v);/* update existing or define global-ish */

/* standard library registration */
void stdlib_register(Interp *ip);
void register_native(Interp *ip, const char *name,
                     Value (*fn)(Interp*, Value*, int));

/* used by builtins */
FuncDef *find_func(Interp *ip, const char *name);
ClassDef *find_class(Interp *ip, const char *name);

Value call_value(Interp *ip, Value fn, Value *args, int nargs);

#endif /* LOOM_INTERP_H */
