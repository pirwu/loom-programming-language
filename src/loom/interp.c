/* interp.c — tree-walking interpreter for Loom */
#include "interp.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <strings.h>
#include <math.h>

/* ---------------- environment ---------------- */

Env *env_new(Env *parent) {
    Env *e = calloc(1, sizeof(Env));
    e->parent = parent;
    return e;
}

Value *env_get(Env *e, const char *name) {
    for (Env *x = e; x; x = x->parent)
        for (int i = 0; i < x->n; i++)
            if (strcasecmp(x->names[i], name) == 0)
                return &x->vals[i];
    return NULL;
}

void env_set(Env *e, const char *name, Value v) {
    for (int i = 0; i < e->n; i++)
        if (strcasecmp(e->names[i], name) == 0) { e->vals[i] = v; return; }
    if (e->n == e->cap) {
        e->cap = e->cap ? e->cap*2 : 8;
        e->names = realloc(e->names, e->cap*sizeof(char*));
        e->vals  = realloc(e->vals,  e->cap*sizeof(Value));
    }
    e->names[e->n] = strdup(name);
    e->vals[e->n] = v;
    e->n++;
}

int env_assign(Env *e, const char *name, Value v) {
    for (Env *x = e; x; x = x->parent)
        for (int i = 0; i < x->n; i++)
            if (strcasecmp(x->names[i], name) == 0) { x->vals[i] = v; return 1; }
    env_set(e, name, v);
    return 0;
}

/* ---------------- interp basics ---------------- */

void interp_init(Interp *ip) {
    memset(ip, 0, sizeof *ip);
    ip->globals = env_new(NULL);
    stdlib_register(ip);
}

FuncDef *find_func(Interp *ip, const char *name) {
    for (int i = 0; i < ip->nfuncs; i++)
        if (strcasecmp(ip->funcs[i]->name, name) == 0) return ip->funcs[i];
    return NULL;
}

ClassDef *find_class(Interp *ip, const char *name) {
    for (int i = 0; i < ip->nclasses; i++)
        if (strcasecmp(ip->classes[i]->name, name) == 0) return ip->classes[i];
    return NULL;
}

void register_native(Interp *ip, const char *name,
                            Value (*fn)(Interp*, Value*, int)) {
    FuncDef *f = calloc(1, sizeof(FuncDef));
    f->name = strdup(name);
    f->native = fn;
    if (ip->nfuncs == ip->fcap) {
        ip->fcap = ip->fcap ? ip->fcap*2 : 32;
        ip->funcs = realloc(ip->funcs, ip->fcap*sizeof(FuncDef*));
    }
    ip->funcs[ip->nfuncs++] = f;
}

/* forward decls */
static Value eval(Interp *ip, Node *n, Env *env);
static void exec_block(Interp *ip, Node *blk, Env *env);
static void exec_stmt(Interp *ip, Node *n, Env *env);
static Node *mk(NodeType ty, int line) {
    Node *n = calloc(1, sizeof(Node));
    n->type = ty; n->line = line;
    return n;
}

/* ---------------- helpers ---------------- */

static Value rt_error(Interp *ip, const char *fmt, ...) {
    va_list ap; va_start(ap, fmt);
    char buf[512];
    vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    ip->thrown = v_str(buf);
    ip->sig = SIG_THROW;
    longjmp(ip->err_jmp, 1);
    return v_null();
}

Array *array_new(void) {
    Array *a = calloc(1, sizeof(Array));
    return a;
}

static void array_push(Array *a, Value v) {
    if (a->len == a->cap) {
        a->cap = a->cap ? a->cap*2 : 8;
        a->items = realloc(a->items, a->cap*sizeof(Value));
    }
    a->items[a->len++] = v;
}

/* make value of declared type (used by stdlib helpers) */
Value coerce_type(int tok, Value v);
Value coerce_type(int tok, Value v) {
    switch (tok) {
    case T_INT_KW:  return v_int(v_as_int(v));
    case T_BYTE_KW: return v_int(v_as_int(v) & 0xFF);
    case T_DOUBLE_KW: return v_double(v_as_double(v));
    case T_STR_KW:  return v_str(v_to_cstr(v));
    case T_CHAR_KW: {
        if (v.type == V_STR && v.u.s && v.u.s[0]) return v_char((unsigned char)v.u.s[0]);
        return v_char(v_as_int(v));
    }
    default: return v;
    }
}

/* ---------------- operators ---------------- */

static Value arith(OpKind op, Value a, Value b) {
    /* string concat with + */
    if (op == OP_ADD && (a.type == V_STR || b.type == V_STR)) {
        char *x = malloc(strlen(v_to_cstr(a)) + strlen(v_to_cstr(b)) + 1);
        sprintf(x, "%s%s", v_to_cstr(a), v_to_cstr(b));
        return v_str_take(x);
    }
    if (op == OP_IS) return v_bool(a.type == b.type && v_eq(a,b));
    int both_int = (a.type!=V_DOUBLE && b.type!=V_DOUBLE &&
                    a.type!=V_STR && b.type!=V_STR);
    if (both_int) {
        int64_t x = v_as_int(a), y = v_as_int(b);
        switch (op) {
        case OP_ADD: return v_int(x+y);
        case OP_SUB: return v_int(x-y);
        case OP_MUL: return v_int(x*y);
        case OP_DIV:
            if (y == 0) break;   /* fall through to double div */
            return v_int(x / y);
        case OP_MOD:
            if (y == 0) break;
            return v_int(x % y);
        case OP_POW: { double r = pow((double)x,(double)y);
                       if (r == floor(r) && fabs(r) < 9e18) return v_int((int64_t)r);
                       return v_double(r); }
        case OP_BAND: return v_int(x & y);
        case OP_BOR:  return v_int(x | y);
        case OP_BXOR: return v_int(x ^ y);
        case OP_SHL:  return v_int((uint64_t)x << (y & 63));
        case OP_SHR:  return v_int((uint64_t)x >> (y & 63));
        default: break;
        }
    }
    double x = v_as_double(a), y = v_as_double(b);
    switch (op) {
    case OP_ADD: return v_double(x+y);
    case OP_SUB: return v_double(x-y);
    case OP_MUL: return v_double(x*y);
    case OP_DIV: return v_double(x/y);
    case OP_MOD: return v_double(fmod(x,y));
    case OP_POW: return v_double(pow(x,y));
    default: break;
    }
    return v_double(x);
}
static Value compare_op(OpKind op, Value a, Value b) {
    if (op == OP_EQ)  return v_bool(v_eq(a,b));
    if (op == OP_NEQ) return v_bool(!v_eq(a,b));
    if (op == OP_IS)  return v_bool(a.type==b.type && v_eq(a,b));
    int cmp;
    if (a.type == V_STR || b.type == V_STR)
        cmp = strcmp(v_to_cstr(a), v_to_cstr(b));
    else if (a.type==V_DOUBLE || b.type==V_DOUBLE) {
        double x=v_as_double(a), y=v_as_double(b);
        cmp = x<y ? -1 : (x>y ? 1 : 0);
    } else {
        int64_t x=v_as_int(a), y=v_as_int(b);
        cmp = x<y ? -1 : (x>y ? 1 : 0);
    }
    switch (op) {
    case OP_LT: return v_bool(cmp<0);
    case OP_GT: return v_bool(cmp>0);
    case OP_LE: return v_bool(cmp<=0);
    case OP_GE: return v_bool(cmp>=0);
    default: return v_bool(false);
    }
}

/* ---------------- calls ---------------- */

Value call_value(Interp *ip, Value fn, Value *args, int nargs) {
    if (fn.type == V_FUNC || fn.type == V_LAMBDA) {
        FuncDef *f = (FuncDef*)fn.u.call.fn;
        if (f->native) return f->native(ip, args, nargs);
        Env *call_env = env_new(f->closure ? f->closure : ip->globals);
        for (int i = 0; i < f->np; i++)
            env_set(call_env, f->params[i], i < nargs ? args[i] : v_null());
        /* ARGS pseudo-array */
        Array *aa = array_new();
        for (int i = 0; i < nargs; i++) array_push(aa, args[i]);
        Value av = {V_ARRAY,{0}}; av.u.arr = aa;
        env_set(call_env, "ARGS", av);
        Signal save = ip->sig; ip->sig = SIG_NONE;
        exec_block(ip, f->body, call_env);
        Value ret = ip->retval;
        ip->retval = (save==SIG_RETURN) ? ret : v_null();
        if (save != SIG_RETURN) ip->sig = save; /* propagate other signals */
        return ret;
    }
    return rt_error(ip, "call of non-function value");
}

/* ---------------- statement execution ---------------- */

static void exec_block(Interp *ip, Node *blk, Env *env) {
    if (!blk) return;
    for (int i = 0; i < blk->u.block.n; i++) {
        if (ip->sig != SIG_NONE) return;
        exec_stmt(ip, blk->u.block.stmts[i], env);
    }
}

static void collect_labels(Interp *ip, Node *blk) {
    for (int i = 0; i < blk->u.block.n; i++) {
        Node *st = blk->u.block.stmts[i];
        if (st->type == S_LABEL) {
            if (ip->nlabels == ip->lcap) {
                ip->lcap = ip->lcap ? ip->lcap*2 : 16;
                ip->labels = realloc(ip->labels, ip->lcap*sizeof(*ip->labels));
            }
            ip->labels[ip->nlabels].name = st->u.ident.name;
            ip->labels[ip->nlabels].stmt_index = &blk->u.block.stmts[i];
            ip->nlabels++;
        }
    }
}

static int label_index(Interp *ip, const char *name) {
    for (int i = 0; i < ip->nlabels; i++)
        if (strcasecmp(ip->labels[i].name, name) == 0)
            /* index within main_block */
            for (int j = 0; j < ip->main_block->u.block.n; j++)
                if (&ip->main_block->u.block.stmts[j] == ip->labels[i].stmt_index ||
                    ip->main_block->u.block.stmts[j] == *ip->labels[i].stmt_index)
                    return j;
    return -1;
}

static void run_main_block(Interp *ip, Node *prog) {
    ip->main_block = prog;
    collect_labels(ip, prog);
    ip->pc = 0;
    while (ip->pc < prog->u.block.n) {
        if (ip->sig != SIG_NONE && ip->sig != SIG_GOTO && ip->sig != SIG_GOSUB) break;
        if (ip->sig == SIG_GOTO || ip->sig == SIG_GOSUB) {
            Signal s = ip->sig;
            ip->sig = SIG_NONE;
            int idx = label_index(ip, ip->goto_target);
            if (idx < 0) { rt_error(ip, "unknown label '%s'", ip->goto_target); }
            if (s == SIG_GOSUB) {
                if (ip->ngosub == ip->gcap) {
                    ip->gcap = ip->gcap?ip->gcap*2:16;
                    ip->gosub_stack = realloc(ip->gosub_stack, ip->gcap*sizeof(int));
                }
                ip->gosub_stack[ip->ngosub++] = ip->pc;
            }
            ip->pc = idx;
            continue;
        }
        exec_stmt(ip, prog->u.block.stmts[ip->pc], ip->globals);
        ip->pc++;
    }
}

static void exec_stmt(Interp *ip, Node *n, Env *env) {
    switch (n->type) {
    case S_LET: {
        Value v = n->u.let.decl.init ? eval(ip, n->u.let.decl.init, env) : v_null();
        switch (n->u.let.decl.type_ann) {
        case T_INT_KW:   v = v_int(v_as_int(v)); break;
        case T_BYTE_KW:  v = v_int(v_as_int(v) & 0xFF); break;
        case T_DOUBLE_KW: v = v_double(v_as_double(v)); break;
        case T_STR_KW:   { const char *t = v_to_cstr(v); v = v_str(t); } break;
        case T_CHAR_KW: {
            if (v.type == V_STR && v.u.s && v.u.s[0]) v = v_char((unsigned char)v.u.s[0]);
            else v = v_char(v_as_int(v));
            break;
        }
        default: break;
        }
        env_set(env, n->u.let.decl.name, v);
        return;
    }
    case S_ASSIGN: {
        Node *t = n->u.assign.target;
        Value v = eval(ip, n->u.assign.value, env);
        if (t->type == E_IDENT) { env_assign(env, t->u.ident.name, v); return; }
        if (t->type == E_INDEX) {
            Value obj = eval(ip, t->u.index.obj, env);
            Value idx = eval(ip, t->u.index.idx, env);
            if (obj.type == V_ARRAY) {
                int64_t i = v_as_int(idx);
                Array *a = obj.u.arr;
                if (i < 0) i += (int64_t)a->len;
                if (i < 0 || (size_t)i >= a->len) {
                    while ((size_t)i >= a->len) array_push(a, v_null());
                }
                a->items[i] = v; return;
            }
            if (obj.type == V_STR) { /* strings immutable: rebuild */
                int64_t i = v_as_int(idx);
                char *s = obj.u.s; size_t L = strlen(s);
                if (i<0 || (size_t)i>=L) rt_error(ip,"index out of range");
                char *ns = strdup(s); ns[i] = (char)v_as_int(v);
                /* find holder and replace */
                Value *slot = NULL;
                if (t->u.index.obj->type == E_IDENT) slot = env_get(env, t->u.index.obj->u.ident.name);
                if (slot) { free(slot->u.s); slot->u.s = ns; } else free(ns);
                return;
            }
            rt_error(ip, "cannot index-assign this value");
        }
        if (t->type == E_FIELD) {
            Value obj = eval(ip, t->u.field.target, env);
            if (obj.type == V_OBJECT) {
                Object *o = obj.u.obj;
                ClassDef *cd = LOOM_CLASSDEF(o->cls);
                for (int i = 0; i < cd->nf; i++)
                    if (strcasecmp(cd->fields[i], t->u.field.field)==0) { o->fields[i]=v; return; }
                /* dynamic field: append */
                cd->fields = realloc(cd->fields, (cd->nf+1)*sizeof(char*));
                o->fields  = realloc(o->fields,  (cd->nf+1)*sizeof(Value));
                cd->fields[cd->nf] = strdup(t->u.field.field);
                o->fields[cd->nf] = v;
                cd->nf++; o->nfields++;
                return;
            }
            rt_error(ip, "field assignment on non-object");
        }
        rt_error(ip, "invalid assignment target");
        return;
    }
    case S_EXPR: case S_CALL: {
        eval(ip, n->u.call.callee, env);
        return;
    }
    case S_CONSOLE: {
        for (int i = 0; i < n->u.call.nargs; i++) {
            Value v = eval(ip, n->u.call.args[i], env);
            printf("%s", v_to_cstr(v));
            if (i + 1 < n->u.call.nargs) printf(" ");
        }
        printf("\n");
        fflush(stdout);
        return;
    }
    case S_INPUT: {
        char buf[4096];
        if (!fgets(buf, sizeof buf, stdin)) { buf[0]=0; }
        size_t L = strlen(buf);
        if (L && buf[L-1]=='\n') buf[--L]=0;
        if (n->u.solo.single)
            env_assign(env, n->u.solo.single->u.ident.name, v_str(buf));
        else
            printf("%s", buf);
        return;
    }
    case S_IF: {
        Value c = eval(ip, n->u.iff.cond, env);
        if (v_truthy(c)) exec_block(ip, n->u.iff.then, env);
        else if (n->u.iff.els) exec_block(ip, n->u.iff.els, env);
        return;
    }
    case S_FOR: {
        if (n->u.foor.invar) {
            Value it = eval(ip, n->u.foor.iterable, env);
            Env *le = env_new(env);
            ip->in_loop++;
            if (it.type == V_ARRAY) {
                for (size_t i = 0; i < it.u.arr->len; i++) {
                    env_set(le, n->u.foor.invar, it.u.arr->items[i]);
                    exec_block(ip, n->u.foor.body, le);
                    if (ip->sig==SIG_EXIT_LOOP) { ip->sig=SIG_NONE; break; }
                    if (ip->sig!=SIG_NONE) { ip->in_loop--; return; }
                }
            } else if (it.type == V_STR) {
                for (const char *q = it.u.s; *q; q++) {
                    env_set(le, n->u.foor.invar, v_char((unsigned char)*q));
                    exec_block(ip, n->u.foor.body, le);
                    if (ip->sig==SIG_EXIT_LOOP) { ip->sig=SIG_NONE; break; }
                    if (ip->sig!=SIG_NONE) { ip->in_loop--; return; }
                }
            } else if (it.type == V_INT) {
                for (int64_t k = 0; k < v_as_int(it); k++) {
                    env_set(le, n->u.foor.invar, v_int(k));
                    exec_block(ip, n->u.foor.body, le);
                    if (ip->sig==SIG_EXIT_LOOP) { ip->sig=SIG_NONE; break; }
                    if (ip->sig!=SIG_NONE) { ip->in_loop--; return; }
                }
            }
            ip->in_loop--;
            return;
        }
        Value from = eval(ip, n->u.foor.from, env);
        Value to   = eval(ip, n->u.foor.to, env);
        Value step = n->u.foor.step ? eval(ip, n->u.foor.step, env) : v_int(1);
        Env *le = env_new(env);
        int isdbl = from.type==V_DOUBLE||to.type==V_DOUBLE||step.type==V_DOUBLE;
        ip->in_loop++;
        if (!isdbl) {
            int64_t f=v_as_int(from), t=v_as_int(to), s=v_as_int(step);
            if (s == 0) rt_error(ip, "FOR STEP cannot be 0");
            for (int64_t k = f; s>0 ? k<=t : k>=t; k += s) {
                env_set(le, n->u.foor.var, v_int(k));
                exec_block(ip, n->u.foor.body, le);
                if (ip->sig==SIG_EXIT_LOOP) { ip->sig=SIG_NONE; break; }
                if (ip->sig!=SIG_NONE) { ip->in_loop--; return; }
            }
        } else {
            double f=v_as_double(from), t=v_as_double(to), s=v_as_double(step);
            for (double k=f; s>0 ? k<=t : k>=t; k+=s) {
                env_set(le, n->u.foor.var, v_double(k));
                exec_block(ip, n->u.foor.body, le);
                if (ip->sig==SIG_EXIT_LOOP) { ip->sig=SIG_NONE; break; }
                if (ip->sig!=SIG_NONE) { ip->in_loop--; return; }
            }
        }
        ip->in_loop--;
        return;
    }
    case S_WHILE: {
        ip->in_loop++;
        while (v_truthy(eval(ip, n->u.whl.cond, env))) {
            exec_block(ip, n->u.whl.body, env);
            if (ip->sig==SIG_EXIT_LOOP) { ip->sig=SIG_NONE; break; }
            if (ip->sig!=SIG_NONE) { ip->in_loop--; return; }
        }
        ip->in_loop--;
        return;
    }
    case S_DOWHILE: {
        ip->in_loop++;
        do {
            exec_block(ip, n->u.dowhile.body, env);
            if (ip->sig==SIG_EXIT_LOOP) { ip->sig=SIG_NONE; break; }
            if (ip->sig!=SIG_NONE) { ip->in_loop--; return; }
        } while (!v_truthy(eval(ip, n->u.dowhile.cond, env)));
        ip->in_loop--;
        return;
    }
    case S_EXIT: ip->sig = ip->in_loop ? SIG_EXIT_LOOP : ip->sig; return;
    case S_BREAK: ip->sig = SIG_BREAK; return;
    case S_GOTO:
        ip->sig = SIG_GOTO; ip->goto_target = n->u.goto_.label; return;
    case S_GOSUB:
        ip->sig = SIG_GOSUB; ip->goto_target = n->u.goto_.label; return;
    case S_RETURN:
        ip->retval = n->u.retv.value ? eval(ip, n->u.retv.value, env) : v_null();
        if (ip->sig == SIG_GOSUB) { /* RETURN ends GOSUB */
            ip->sig = SIG_NONE;
        } else {
            ip->sig = SIG_RETURN;
        }
        return;
    case S_DEF: {
        FuncDef *f = calloc(1,sizeof(FuncDef));
        f->name = strdup(n->u.def.name);
        f->body = n->u.def.body;
        f->params = n->u.def.params;
        f->np = n->u.def.np;
        f->closure = env;
        if (ip->nfuncs==ip->fcap){ip->fcap=ip->fcap?ip->fcap*2:32;
            ip->funcs=realloc(ip->funcs,ip->fcap*sizeof(FuncDef*));}
        ip->funcs[ip->nfuncs++]=f;
        return;
    }
    case S_CLASS: {
        ClassDef *cd = calloc(1,sizeof(ClassDef));
        cd->name = strdup(n->u.cls.name);
        cd->body = n->u.cls.body;
        cd->env = env_new(ip->globals);
        /* hoist nested DEFs as methods registered under ClassName.method */
        for (int i = 0; i < cd->body->u.block.n; i++) {
            Node *m = cd->body->u.block.stmts[i];
            if (m->type == S_DEF) {
                FuncDef *f = calloc(1,sizeof(FuncDef));
                char *q = malloc(strlen(cd->name)+strlen(m->u.def.name)+2);
                sprintf(q, "%s.%s", cd->name, m->u.def.name);
                f->name = q;
                f->body = m->u.def.body;
                f->params = m->u.def.params;
                f->np = m->u.def.np;
                f->closure = cd->env;
                if (ip->nfuncs==ip->fcap){ip->fcap=ip->fcap?ip->fcap*2:32;
                    ip->funcs=realloc(ip->funcs,ip->fcap*sizeof(FuncDef*));}
                ip->funcs[ip->nfuncs++]=f;
                /* also plain name for direct CALL */
                FuncDef *f2 = calloc(1,sizeof(FuncDef));
                *f2 = *f; f2->name = strdup(m->u.def.name);
                if (ip->nfuncs==ip->fcap){ip->fcap=ip->fcap?ip->fcap*2:32;
                    ip->funcs=realloc(ip->funcs,ip->fcap*sizeof(FuncDef*));}
                ip->funcs[ip->nfuncs++]=f2;
            } else if (m->type == S_LET) {
                cd->fields = realloc(cd->fields,(cd->nf+1)*sizeof(char*));
                cd->fields[cd->nf++] = m->u.let.decl.name;
            }
        }
        if (ip->nclasses==ip->ccap){ip->ccap=ip->ccap?ip->ccap*2:8;
            ip->classes=realloc(ip->classes,ip->ccap*sizeof(ClassDef*));}
        ip->classes[ip->nclasses++]=cd;
        Value cv = {V_CLASS,{0}}; cv.u.cls = LOOM_CLASS_CAST(cd);
        env_set(ip->globals, cd->name, cv);
        return;
    }
    case S_TRY: {
        Signal saved = ip->sig; ip->sig = SIG_NONE;
        Value saved_throw = ip->thrown;
        if (setjmp(ip->err_jmp) == 0) {
            exec_block(ip, n->u.trystmt.tryb, env);
        } else {
            /* caught */
            Env *cenv = env_new(env);
            if (n->u.trystmt.errvar) env_set(cenv, n->u.trystmt.errvar, ip->thrown);
            ip->sig = SIG_NONE;
            exec_block(ip, n->u.trystmt.catchb, cenv);
        }
        if (n->u.trystmt.finallyb) exec_block(ip, n->u.trystmt.finallyb, env);
        if (ip->sig == SIG_NONE) ip->sig = saved;
        ip->thrown = saved_throw;
        return;
    }
    case S_THROW: {
        Value v = eval(ip, n->u.solo.single, env);
        ip->thrown = v;
        ip->sig = SIG_THROW;
        longjmp(ip->err_jmp, 1);
        return;
    }
    case S_SWITCH: {
        Value subj = eval(ip, n->u.swtch.subj, env);
        int matched = 0;
        for (int i = 0; i < n->u.swtch.ncase; i++) {
            Value cv = eval(ip, n->u.swtch.cases[i], env);
            if (v_eq(subj, cv)) {
                matched = 1;
                Env *benv = env_new(env);
                exec_block(ip, n->u.swtch.bodies[i], benv);
                if (ip->sig == SIG_BREAK) ip->sig = SIG_NONE;
                break;
            }
        }
        if (!matched && n->u.swtch.dflt) {
            Env *benv = env_new(env);
            exec_block(ip, n->u.swtch.dflt, benv);
            if (ip->sig == SIG_BREAK) ip->sig = SIG_NONE;
        }
        return;
    }
    case S_IMPORT: {
        /* import file relative to program dir or lib/ */
        char path[1024];
        snprintf(path,sizeof path,"%s",n->u.imp.mod);
        FILE *f = fopen(path,"rb");
        if (!f) {
            char *dot = strrchr(path,'.');
            if (!dot) { snprintf(path,sizeof path,"%s.loom",n->u.imp.mod); f=fopen(path,"rb"); }
        }
        if (!f) { snprintf(path,sizeof path,"lib/%s.loom",n->u.imp.mod); f=fopen(path,"rb"); }
        if (!f) { rt_error(ip,"import: cannot open module '%s'", n->u.imp.mod); return; }
        fseek(f,0,SEEK_END); long sz=ftell(f); fseek(f,0,SEEK_SET);
        char *src = malloc(sz+1); fread(src,1,sz,f); src[sz]=0; fclose(f);
        int tn; Token *toks = lex(src,&tn);
        Node *mod = parse_program(toks,tn);
        run_main_block(ip, mod);
        return;
    }
    case S_REFLECT: {
        Value v = eval(ip, n->u.reflect.x, env);
        printf("REFLECT type=%d value=%s\n", (int)v.type, v_to_cstr(v));
        return;
    }
    case S_LABEL: return;
    case S_BLOCK: exec_block(ip, n, env); return;
    default:
        eval(ip, n, env);
        return;
    }
}

/* ---------------- expression evaluation ---------------- */

static Value eval(Interp *ip, Node *n, Env *env) {
    switch (n->type) {
    case E_INT:    return v_int(n->u.ival.i);
    case E_DOUBLE: return v_double(n->u.dval.d);
    case E_STR:    return v_str(n->u.sval.s);
    case E_GROUPED: return eval(ip, n->u.un.arg, env);
    case E_IDENT: {
        Value *v = env_get(env, n->u.ident.name);
        if (v) return *v;
        FuncDef *f = find_func(ip, n->u.ident.name);
        if (f) { Value fv={V_FUNC,{0}}; fv.u.call.fn=f; return fv; }
        ClassDef *cd = find_class(ip, n->u.ident.name);
        if (cd) { Value cv={V_CLASS,{0}}; cv.u.cls=LOOM_CLASS_CAST(cd); return cv; }
        /* unknown identifier evaluates to NULL instead of crashing */
        return v_null();
    }
    case E_BIN: {
        OpKind op = n->u.bin.op;
        if (op == OP_AND) {
            Value a = eval(ip,n->u.bin.a,env);
            if (!v_truthy(a)) return v_bool(false);
            return v_bool(v_truthy(eval(ip,n->u.bin.b,env)));
        }
        if (op == OP_OR) {
            Value a = eval(ip,n->u.bin.a,env);
            if (v_truthy(a)) return v_bool(true);
            return v_bool(v_truthy(eval(ip,n->u.bin.b,env)));
        }
        Value a = eval(ip,n->u.bin.a,env);
        Value b = eval(ip,n->u.bin.b,env);
        switch (op) {
        case OP_EQ: case OP_NEQ: case OP_LT: case OP_GT: case OP_LE: case OP_GE: case OP_IS:
            return compare_op(op,a,b);
        default:
            return arith(op,a,b);
        }
    }
    case E_UN: {
        OpKind op = n->u.bin.op;
        if (op == OP_LNOT) return v_bool(!v_truthy(eval(ip,n->u.bin.a,env)));
        Value a = eval(ip,n->u.bin.a,env);
        if (op == OP_NEG) {
            if (a.type==V_DOUBLE) return v_double(-a.u.d);
            return v_int(-v_as_int(a));
        }
        return a;
    }
    case E_INDEX: {
        Value obj = eval(ip,n->u.index.obj,env);
        Value idx = eval(ip,n->u.index.idx,env);
        if (obj.type == V_ARRAY) {
            int64_t i = v_as_int(idx);
            Array *a = obj.u.arr;
            if (i<0) i += (int64_t)a->len;
            if (i<0 || (size_t)i>=a->len) return v_null();
            return a->items[i];
        }
        if (obj.type == V_STR) {
            int64_t i = v_as_int(idx);
            size_t L = strlen(obj.u.s);
            if (i<0) i += (int64_t)L;
            if (i<0 || (size_t)i>=L) return v_str("");
            char b[2] = { obj.u.s[i], 0 };
            return v_str(b);
        }
        if (obj.type == V_OBJECT) {
            Object *o = obj.u.obj;
            const char *key = v_to_cstr(idx);
            for (int k = 0; k < (int)o->nfields; k++)
                if (strcasecmp(LOOM_CLASSDEF(o->cls)->fields[k], key)==0) return o->fields[k];
            return v_null();
        }
        if (obj.type == V_CLASS) {
            Object dummy; (void)dummy;
            return v_null();
        }
        return v_null();
    }
    case E_FIELD: {
        Value obj = eval(ip,n->u.field.target,env);
        if (obj.type == V_OBJECT) {
            Object *o = obj.u.obj;
            for (int k = 0; k < (int)o->nfields; k++)
                if (strcasecmp(LOOM_CLASSDEF(o->cls)->fields[k], n->u.field.field)==0) return o->fields[k];
            return v_null();
        }
        if (obj.type == V_CLASS) {
            char *q = malloc(strlen(LOOM_CLASSDEF(obj.u.cls)->name)+strlen(n->u.field.field)+2);
            sprintf(q,"%s.%s",LOOM_CLASSDEF(obj.u.cls)->name,n->u.field.field);
            FuncDef *f = find_func(ip,q);
            free(q);
            if (f) { Value fv={V_FUNC,{0}}; fv.u.call.fn=f; return fv; }
            return v_null();
        }
        return v_null();
    }
    case E_ARRAYLIT: {
        Array *a = array_new();
        for (int i = 0; i < n->u.arrlit.n; i++)
            array_push(a, eval(ip,n->u.arrlit.items[i],env));
        Value v = {V_ARRAY,{0}}; v.u.arr=a; return v;
    }
    case E_LAMBDA: {
        FuncDef *f = calloc(1,sizeof(FuncDef));
        f->name = strdup("<lambda>");
        f->params = n->u.lam.params;
        f->np = n->u.lam.np;
        f->closure = env;
        if (n->u.lam.is_expr) {
            /* wrap expression into a RETURN stmt block */
            Node *blk = mk(S_BLOCK, n->line);
            blk->u.block.stmts = malloc(sizeof(Node*));
            blk->u.block.n = 1;
            Node *r = mk(S_RETURN, n->line);
            r->u.retv.value = n->u.lam.body;
            blk->u.block.stmts[0] = r;
            f->body = blk;
        } else {
            f->body = n->u.lam.body;
        }
        Value fv = {V_LAMBDA,{0}}; fv.u.call.fn = f;
        return fv;
    }
    case E_NEW: {
        Value callee = eval(ip, n->u.new_.fn, env);
        if (callee.type == V_CLASS) {
            ClassDef *cd = LOOM_CLASSDEF(callee.u.cls);
            Object *o = calloc(1,sizeof(Object));
            o->cls = LOOM_CLASS_CAST(cd);
            o->nfields = cd->nf;
            o->fields = calloc(cd->nf ? cd->nf : 1, sizeof(Value));
            for (int i = 0; i < cd->nf; i++) o->fields[i] = v_null();
            Value ov = {V_OBJECT,{0}}; ov.u.obj = o;
            /* run constructor named same as class if present */
            FuncDef *ctor = find_func(ip, cd->name);
            if (ctor && ctor->body) {
                Value args[16];
                for (int i = 0; i < n->u.new_.nargs && i < 16; i++)
                    args[i] = eval(ip, n->u.new_.args[i], env);
                /* bind 'self' via first param trick: set in closure env */
                env_set(ctor->closure, "SELF", ov);
                Value fv = {V_FUNC,{0}}; fv.u.call.fn = ctor;
                call_value(ip, fv, args, n->u.new_.nargs);
            }
            return ov;
        }
        /* generic new(fn): treat callee as factory function */
        Value args[16];
        for (int i = 0; i < n->u.new_.nargs && i < 16; i++)
            args[i] = eval(ip, n->u.new_.args[i], env);
        return call_value(ip, callee, args, n->u.new_.nargs < 16 ? n->u.new_.nargs : 16);
    }
    case E_CALL: {
        Value callee = eval(ip, n->u.call.callee, env);
        /* method-style: obj.field(args) where field resolves on object */
        Value args[32]; int na = n->u.call.nargs > 32 ? 32 : n->u.call.nargs;
        for (int i = 0; i < na; i++) args[i] = eval(ip, n->u.call.args[i], env);
        if (callee.type == V_NULL) {
            /* maybe user variable holding func */
            return rt_error(ip, "attempt to call non-function");
        }
        return call_value(ip, callee, args, na);
    }
    default:
        return v_null();
    }
}

/* ---------------- public run ---------------- */

Value interp_run(Interp *ip, Node *prog) {
    if (setjmp(ip->err_jmp) != 0) {
        fprintf(stderr, "runtime error: %s\n", v_to_cstr(ip->thrown));
        exit(1);
    }
    /* pre-pass: hoist DEF/S_CLASS so order doesn't matter */
    for (int i = 0; i < prog->u.block.n; i++) {
        Node *st = prog->u.block.stmts[i];
        if (st->type == S_DEF || st->type == S_CLASS) exec_stmt(ip, st, ip->globals);
    }
    run_main_block(ip, prog);
    return ip->retval;
}
