/* parser.c — recursive-descent / statement parser for Loom */
#include "parser.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

typedef struct { Token *t; int n, p; } P;

static Node *mk(NodeType ty, int line) {
    Node *n = calloc(1, sizeof(Node));
    n->type = ty; n->line = line;
    return n;
}

static Token *cur(P *p)  { return &p->t[p->p < p->n ? p->p : p->n-1]; }
static TokType ct(P *p)  { return cur(p)->type; }
static void adv(P *p)    { if (p->p < p->n-1) p->p++; }
static void skip_nl(P *p){ while (ct(p) == T_NL || ct(p) == T_SEMI) adv(p); }
static int at(P *p, TokType t) { return ct(p) == t; }
static int eat(P *p, TokType t) { if (ct(p)==t) { adv(p); return 1; } return 0; }
static void expect(P *p, TokType t, const char *what) {
    if (!eat(p, t)) {
        fprintf(stderr, "parse error: expected %s at line %d (got '%s')\n",
                what, cur(p)->line, cur(p)->text ? cur(p)->text : "?");
        exit(1);
    }
}

static Node *parse_stmt(P *p);
static Node *parse_expr(P *p);

static char *dup_text(Token *t) { return strdup(t->text ? t->text : ""); }

/* forward declarations */
static Node *parse_block_until(P *p, TokType term1);
static Node *parse_block_until_multi(P *p, const TokType *terms, int nt);
static Node *parse_if_chain(P *p);

/* ------- expression grammar (precedence climbing) ------- */

typedef struct { OpKind op; int prec; } BinInfo;

static int bin_for(TokType t, BinInfo *out) {
    switch (t) {
    case T_OR:     out->op=OP_OR;   out->prec=1; return 1;
    case T_AND:    out->op=OP_AND;  out->prec=2; return 1;
    case T_IS:     out->op=OP_IS;   out->prec=3; return 1;
    case T_ASSIGN: /* '=' used as equality inside expressions handled by caller */
    case T_NEQ:    out->op=OP_NEQ;  out->prec=4; return 1;
    case T_LT:     out->op=OP_LT;   out->prec=5; return 1;
    case T_GT:     out->op=OP_GT;   out->prec=5; return 1;
    case T_LE:     out->op=OP_LE;   out->prec=5; return 1;
    case T_GE:     out->op=OP_GE;   out->prec=5; return 1;
    default: return 0;
    }
}

static int addsub(TokType t, OpKind *op) {
    if (t==T_PLUS)  { *op=OP_ADD; return 1; }
    if (t==T_MINUS) { *op=OP_SUB; return 1; }
    return 0;
}
static int muldiv(TokType t, OpKind *op) {
    if (t==T_STAR)  { *op=OP_MUL; return 1; }
    if (t==T_SLASH) { *op=OP_DIV; return 1; }
    if (t==T_MOD)   { *op=OP_MOD; return 1; }
    return 0;
}
static int bitops(TokType t, OpKind *op) {
    if (t==T_SHL)  { *op=OP_SHL; return 1; }
    if (t==T_SHR)  { *op=OP_SHR; return 1; }
    return 0;
}

static Node *parse_primary(P *p) {
    Token *t = cur(p);
    switch (t->type) {
    case T_INT:    { Node *n = mk(E_INT,t->line); n->u.ival.i = v_as_int(t->val); adv(p); return n; }
    case T_DOUBLE: { Node *n = mk(E_DOUBLE,t->line); n->u.dval.d = t->val.u.d; adv(p); return n; }
    case T_STR:    { Node *n = mk(E_STR,t->line); n->u.sval.s = dup_text(t); adv(p); return n; }
    case T_LPAREN: {
        adv(p); skip_nl(p);
        Node *e = parse_expr(p);
        skip_nl(p);
        expect(p, T_RPAREN, ")");
        Node *g = mk(E_GROUPED, t->line); g->u.un.arg = e; return g;
    }
    case T_LBRACK: { /* array literal [a,b,c] */
        adv(p);
        Node *n = mk(E_ARRAYLIT, t->line);
        int cap = 8; n->u.arrlit.items = malloc(cap*sizeof(Node*));
        skip_nl(p);
        while (!at(p,T_RBRACK) && !at(p,T_EOF_TOK)) {
            Node *e = parse_expr(p);
            if (n->u.arrlit.n == cap) { cap*=2; n->u.arrlit.items=realloc(n->u.arrlit.items,cap*sizeof(Node*)); }
            n->u.arrlit.items[n->u.arrlit.n++] = e;
            skip_nl(p);
            eat(p, T_COMMA);
            skip_nl(p);
        }
        expect(p, T_RBRACK, "]");
        return n;
    }
    case T_NOT: {
        adv(p);
        Node *n = mk(E_UN, t->line);
        n->u.bin.op = OP_LNOT; n->u.bin.a = parse_expr(p); n->u.bin.b = NULL;
        return n;
    }
    case T_MINUS: case T_PLUS: {
        OpKind ok = (t->type==T_MINUS)?OP_NEG:OP_POS;
        adv(p);
        Node *n = mk(E_UN, t->line);
        n->u.bin.op = ok; n->u.bin.a = parse_primary(p); n->u.bin.b=NULL;
        return n;
    }
    case T_NEW: {
        adv(p);
        Node *callee = parse_primary(p);
        Node *n = mk(E_NEW, t->line);
        n->u.new_.fn = callee;
        int cap=8; n->u.new_.args = malloc(cap*sizeof(Node*)); n->u.new_.nargs=0;
        if (eat(p, T_LPAREN)) {
            skip_nl(p);
            while (!at(p,T_RPAREN) && !at(p,T_EOF_TOK)) {
                Node *e = parse_expr(p);
                if (n->u.new_.nargs==cap){cap*=2;n->u.new_.args=realloc(n->u.new_.args,cap*sizeof(Node*));}
                n->u.new_.args[n->u.new_.nargs++] = e;
                skip_nl(p); eat(p,T_COMMA); skip_nl(p);
            }
            expect(p,T_RPAREN,")");
        }
        return n;
    }
    case T_LAMBDA: {
        adv(p);
        Node *n = mk(E_LAMBDA, t->line);
        int cap=8; n->u.lam.params = malloc(cap*sizeof(char*)); n->u.lam.np=0;
        if (eat(p,T_LPAREN)) {
            while (!at(p,T_RPAREN) && !at(p,T_EOF_TOK)) {
                if (n->u.lam.np==cap){cap*=2;n->u.lam.params=realloc(n->u.lam.params,cap*sizeof(char*));}
                n->u.lam.params[n->u.lam.np++] = dup_text(cur(p));
                adv(p); eat(p,T_COMMA);
            }
            expect(p,T_RPAREN,")");
        }
        skip_nl(p);
        /* body: either single expression terminated by END, or block until END */
        if (at(p, T_LBRACE)) {
            adv(p);
            n->u.lam.body = parse_block_until(p, T_RBRACE);
            eat(p, T_RBRACE);
            n->u.lam.is_expr = 0;
        } else {
            /* try expression first; if next token is END treat as expr; else block */
            size_t save = p->p;
            Node *e = parse_expr(p);
            skip_nl(p);
            if (at(p, T_END) || at(p, T_RPAREN)) {
                n->u.lam.body = e; n->u.lam.is_expr = 1;
            } else {
                /* wasn't a plain expr-only lambda; continue as block statements */
                Node *blk = mk(S_BLOCK, t->line);
                int bcap=8; blk->u.block.stmts=malloc(bcap*sizeof(Node*)); blk->u.block.n=0;
                /* re-add e if it was complete */
                blk->u.block.stmts[blk->u.block.n++] = e;
                while (!at(p,T_END) && !at(p,T_EOF_TOK)) {
                    skip_nl(p);
                    if (at(p,T_END)) break;
                    Node *st = parse_stmt(p);
                    if (blk->u.block.n==bcap){bcap*=2;blk->u.block.stmts=realloc(blk->u.block.stmts,bcap*sizeof(Node*));}
                    blk->u.block.stmts[blk->u.block.n++] = st;
                }
                n->u.lam.body = blk; n->u.lam.is_expr = 0;
                (void)save;
            }
            eat(p, T_END);
        }
        return n;
    }
    case T_IDENT: {
        Node *n = mk(E_IDENT, t->line);
        n->u.ident.name = dup_text(t);
        adv(p);
        return n;
    }
    default:
        fprintf(stderr, "parse error: unexpected token '%s' at line %d\n",
                t->text ? t->text : tok_name(t->type), t->line);
        exit(1);
    }
}

static Node *parse_postfix(P *p) {
    Node *e = parse_primary(p);
    while (1) {
        if (at(p, T_LPAREN)) { /* call */
            adv(p);
            Node *c = mk(E_CALL, cur(p)->line);
            c->u.call.callee = e;
            int cap=8; c->u.call.args=malloc(cap*sizeof(Node*)); c->u.call.nargs=0;
            skip_nl(p);
            while (!at(p,T_RPAREN) && !at(p,T_EOF_TOK)) {
                Node *a = parse_expr(p);
                if (c->u.call.nargs==cap){cap*=2;c->u.call.args=realloc(c->u.call.args,cap*sizeof(Node*));}
                c->u.call.args[c->u.call.nargs++] = a;
                skip_nl(p); eat(p,T_COMMA); skip_nl(p);
            }
            expect(p,T_RPAREN,")");
            e = c;
        } else if (at(p, T_LBRACK)) { /* index */
            adv(p);
            Node *ix = mk(E_INDEX, cur(p)->line);
            ix->u.index.obj = e;
            ix->u.index.idx = parse_expr(p);
            expect(p,T_RBRACK,"]");
            e = ix;
        } else if (at(p, T_DOT)) { /* field */
            adv(p);
            Node *f = mk(E_FIELD, cur(p)->line);
            f->u.field.target = e;
            f->u.field.field = dup_text(cur(p));
            adv(p);
            e = f;
        } else break;
    }
    return e;
}

static Node *parse_pow(P *p) {
    Node *lhs = parse_postfix(p);
    if (at(p, T_CARET)) {
        adv(p);
        Node *rhs = parse_pow(p); /* right assoc */
        Node *n = mk(E_BIN, lhs->line);
        n->u.bin.op = OP_POW; n->u.bin.a = lhs; n->u.bin.b = rhs;
        return n;
    }
    return lhs;
}

static Node *parse_mul(P *p) {
    Node *lhs = parse_pow(p);
    OpKind ok;
    while (muldiv(ct(p), &ok)) {
        adv(p); skip_nl(p);
        Node *rhs = parse_pow(p);
        Node *n = mk(E_BIN, lhs->line);
        n->u.bin.op = ok; n->u.bin.a = lhs; n->u.bin.b = rhs;
        lhs = n;
    }
    return lhs;
}

static Node *parse_add(P *p) {
    Node *lhs = parse_mul(p);
    OpKind ok;
    while (addsub(ct(p), &ok)) {
        adv(p); skip_nl(p);
        Node *rhs = parse_mul(p);
        Node *n = mk(E_BIN, lhs->line);
        n->u.bin.op = ok; n->u.bin.a = lhs; n->u.bin.b = rhs;
        lhs = n;
    }
    return lhs;
}

static Node *parse_shift(P *p) {
    Node *lhs = parse_add(p);
    OpKind ok;
    while (bitops(ct(p), &ok)) {
        adv(p); skip_nl(p);
        Node *rhs = parse_add(p);
        Node *n = mk(E_BIN, lhs->line);
        n->u.bin.op = ok; n->u.bin.a = lhs; n->u.bin.b = rhs;
        lhs = n;
    }
    return lhs;
}

static Node *parse_compare(P *p) {
    Node *lhs = parse_shift(p);
    BinInfo bi;
    /* handle '&' and '|' bitwise? use words only; also '=' equality when in expr context */
    while (bin_for(ct(p), &bi) || ct(p)==T_ASSIGN) {
        OpKind ok;
        if (ct(p)==T_ASSIGN) ok = OP_EQ;
        else if (ct(p)==T_XORKW) ok = OP_BXOR;
        else ok = bi.op;
        adv(p); skip_nl(p);
        Node *rhs = parse_shift(p);
        Node *n = mk(E_BIN, lhs->line);
        n->u.bin.op = ok; n->u.bin.a = lhs; n->u.bin.b = rhs;
        lhs = n;
        if (ct(p)==T_XORKW) { adv(p); skip_nl(p);
            Node *r2 = parse_shift(p);
            Node *n2 = mk(E_BIN, lhs->line);
            n2->u.bin.op=OP_BXOR; n2->u.bin.a=lhs; n2->u.bin.b=r2; lhs=n2; }
    }
    return lhs;
}

static Node *parse_expr(P *p) {
    return parse_compare(p);
}

/* ------- statements ------- */

static int stmt_end(P *p) {
    return at(p,T_NL) || at(p,T_SEMI) || at(p,T_EOF_TOK);
}
static void finish_line(P *p) {
    while (at(p,T_NL) || at(p,T_SEMI)) adv(p);
}

static Node *parse_block_until(P *p, TokType term1) {
    Node *blk = mk(S_BLOCK, cur(p)->line);
    int cap=16; blk->u.block.stmts=malloc(cap*sizeof(Node*)); blk->u.block.n=0;
    while (1) {
        skip_nl(p);
        if (at(p,T_EOF_TOK)) break;
        if (term1 != T_EOF_TOK && at(p,term1)) break;
        Node *st = parse_stmt(p);
        if (blk->u.block.n==cap){cap*=2;blk->u.block.stmts=realloc(blk->u.block.stmts,cap*sizeof(Node*));}
        blk->u.block.stmts[blk->u.block.n++]=st;
    }
    return blk;
}

/* multi-terminator helper for IF chains etc. */
static int is_term_any(P *p, const TokType *terms, int nt) {
    for (int i=0;i<nt;i++) if (at(p,terms[i])) return 1;
    return 0;
}

static Node *parse_block_until_multi(P *p, const TokType *terms, int nt) {
    Node *blk = mk(S_BLOCK, cur(p)->line);
    int cap=16; blk->u.block.stmts=malloc(cap*sizeof(Node*)); blk->u.block.n=0;
    while (1) {
        skip_nl(p);
        if (at(p,T_EOF_TOK) || is_term_any(p,terms,nt)) break;
        Node *st = parse_stmt(p);
        if (blk->u.block.n==cap){cap*=2;blk->u.block.stmts=realloc(blk->u.block.stmts,cap*sizeof(Node*));}
        blk->u.block.stmts[blk->u.block.n++]=st;
    }
    return blk;
}

static Node *parse_if(P *p) {
    int line = cur(p)->line;
    expect(p, T_IF, "IF");
    Node *cond = parse_expr(p);
    eat(p, T_THEN);
    static const TokType terms[] = {T_ELSEIF, T_ELSE, T_ENDIF};
    Node *thenb = parse_block_until_multi(p, terms, 3);
    Node *n = mk(S_IF, line);
    n->u.iff.cond = cond; n->u.iff.then = thenb; n->u.iff.els = NULL;
    if (at(p, T_ELSEIF)) {
        Node *els = parse_if_chain(p);
        n->u.iff.els = els;
    } else if (eat(p, T_ELSE)) {
        static const TokType t2[] = {T_ENDIF};
        n->u.iff.els = parse_block_until_multi(p, t2, 1);
    }
    expect(p, T_ENDIF, "ENDIF");
    return n;
}

static Node *parse_if_chain(P *p) {
    /* called with cursor on ELSEIF or ELSE */
    int line = cur(p)->line;
    if (eat(p, T_ELSEIF)) {
        Node *cond = parse_expr(p);
        eat(p, T_THEN);
        static const TokType terms[] = {T_ELSEIF, T_ELSE, T_ENDIF};
        Node *body = parse_block_until_multi(p, terms, 3);
        Node *n = mk(S_IF, line);
        n->u.iff.cond = cond; n->u.iff.then = body; n->u.iff.els = NULL;
        if (at(p, T_ELSEIF)) n->u.iff.els = parse_if_chain(p);
        else if (eat(p, T_ELSE)) {
            static const TokType t2[] = {T_ENDIF};
            n->u.iff.els = parse_block_until_multi(p, t2, 1);
        }
        /* ENDIF consumed by outermost */
        return n;
    }
    if (eat(p, T_ELSE)) {
        static const TokType t2[] = {T_ENDIF};
        return parse_block_until_multi(p, t2, 1);
    }
    return NULL;
}

static Node *parse_stmt(P *p) {
    Token *t = cur(p);
    int line = t->line;
    skip_nl(p);
    t = cur(p);
    switch (t->type) {
    case T_LET: case T_DIM: case T_VAR: {
        adv(p);
        Node *n = mk(S_LET, line);
        n->u.let.decl.name = dup_text(cur(p));
        expect(p, T_IDENT, "variable name");
        /* optional type annotation ": STR" etc. */
        if (eat(p, T_COLON)) {
            TokType tt = ct(p);
            if (tt==T_STR_KW||tt==T_INT_KW||tt==T_DOUBLE_KW||tt==T_CHAR_KW||tt==T_BYTE_KW) {
                n->u.let.decl.type_ann = tt; adv(p);
            }
        }
        if (eat(p, T_ASSIGN)) n->u.let.decl.init = parse_expr(p);
        finish_line(p);
        return n;
    }
    case T_CONSOLE: {
        adv(p);
        Node *n = mk(S_CONSOLE, line);
        int cap=8; n->u.call.args=malloc(cap*sizeof(Node*)); n->u.call.nargs=0;
        n->u.call.callee = NULL;
        eat(p, T_LPAREN);
        skip_nl(p);
        while (!stmt_end(p) && !at(p,T_RPAREN)) {
            Node *e = parse_expr(p);
            if (n->u.call.nargs==cap){cap*=2;n->u.call.args=realloc(n->u.call.args,cap*sizeof(Node*));}
            n->u.call.args[n->u.call.nargs++]=e;
            eat(p,T_COMMA); skip_nl(p);
            if (at(p,T_RPAREN)) { adv(p); break; }
        }
        finish_line(p);
        return n;
    }
    case T_INPUT: {
        adv(p);
        Node *n = mk(S_INPUT, line);
        if (at(p,T_IDENT)) { n->u.solo.single = mk(E_IDENT,line);
                             n->u.solo.single->u.ident.name = dup_text(cur(p)); adv(p); }
        finish_line(p);
        return n;
    }
    case T_IF: return parse_if(p);
    case T_FOR: {
        adv(p);
        Node *n = mk(S_FOR, line);
        char *var = dup_text(cur(p));
        expect(p,T_IDENT,"loop variable");
        if (eat(p,T_IN)) {
            n->u.foor.invar = var;
            n->u.foor.iterable = parse_expr(p);
        } else {
            n->u.foor.var = var;
            expect(p,T_ASSIGN,"=");
            n->u.foor.from = parse_expr(p);
            expect(p,T_TO,"TO");
            n->u.foor.to = parse_expr(p);
            if (eat(p,T_STEP)) n->u.foor.step = parse_expr(p);
        }
        eat(p,T_THEN);
        static const TokType terms[]={T_NEXT};
        n->u.foor.body = parse_block_until_multi(p, terms, 1);
        expect(p,T_NEXT,"NEXT");
        finish_line(p);
        return n;
    }
    case T_WHILE: {
        adv(p);
        Node *n = mk(S_WHILE, line);
        n->u.whl.cond = parse_expr(p);
        eat(p,T_THEN);
        static const TokType terms[]={T_WHILEEND};
        n->u.whl.body = parse_block_until_multi(p, terms, 1);
        expect(p,T_WHILEEND,"WHILEEND");
        finish_line(p);
        return n;
    }
    case T_DO: {
        adv(p);
        Node *n = mk(S_DOWHILE, line);
        static const TokType terms[]={T_UNTIL};
        n->u.dowhile.body = parse_block_until_multi(p, terms, 1);
        expect(p,T_UNTIL,"UNTIL");
        n->u.dowhile.cond = parse_expr(p);
        finish_line(p);
        return n;
    }
    case T_EXIT: {
        adv(p); Node *n = mk(S_EXIT,line); finish_line(p); return n;
    }
    case T_BREAKS: { adv(p); Node *n=mk(S_BREAK,line); finish_line(p); return n; }
    case T_GOTO: case T_GOSUB: {
        int isgosub = (t->type==T_GOSUB);
        adv(p);
        Node *n = mk(isgosub?S_GOSUB:S_GOTO, line);
        n->u.goto_.label = dup_text(cur(p));
        adv(p);
        finish_line(p);
        return n;
    }
    case T_RETURN: {
        adv(p);
        Node *n = mk(S_RETURN,line);
        if (!stmt_end(p)) n->u.retv.value = parse_expr(p);
        finish_line(p);
        return n;
    }
    case T_CALL: {
        adv(p);
        Node *inner = parse_postfix(p);
        Node *n = mk(S_CALL,line);
        n->u.call.callee = inner;
        n->u.call.args=NULL; n->u.call.nargs=0;
        finish_line(p);
        return n;
    }
    case T_DEF: {
        adv(p);
        Node *n = mk(S_DEF,line);
        n->u.def.name = dup_text(cur(p));
        expect(p,T_IDENT,"function name");
        int cap=8; n->u.def.params=malloc(cap*sizeof(char*)); n->u.def.np=0;
        if (eat(p,T_LPAREN)) {
            while (!at(p,T_RPAREN)&&!at(p,T_EOF_TOK)) {
                /* skip ARGS keyword */
                if (at(p,T_ARGS)) { adv(p); continue; }
                if (n->u.def.np==cap){cap*=2;n->u.def.params=realloc(n->u.def.params,cap*sizeof(char*));}
                n->u.def.params[n->u.def.np++]=dup_text(cur(p));
                adv(p); eat(p,T_COMMA);
            }
            expect(p,T_RPAREN,")");
        }
        static const TokType terms[]={T_ENDDEF};
        n->u.def.body = parse_block_until_multi(p,terms,1);
        expect(p,T_ENDDEF,"ENDDEF");
        finish_line(p);
        return n;
    }
    case T_CLASS: {
        adv(p);
        Node *n = mk(S_CLASS,line);
        n->u.cls.name = dup_text(cur(p));
        expect(p,T_IDENT,"class name");
        /* optional EXTENDS parent — model 'extends' as identifier keyword-less: accept IDENT named extends? Use ':' or word INHERITS not required; keep simple: skip */
        static const TokType terms[]={T_ENDCLASS};
        n->u.cls.body = parse_block_until_multi(p,terms,1);
        expect(p,T_ENDCLASS,"ENDCLASS");
        finish_line(p);
        return n;
    }
    case T_TRY: {
        adv(p);
        Node *n = mk(S_TRY,line);
        static const TokType terms[]={T_CATCH,T_FINALLY,T_END};
        n->u.trystmt.tryb = parse_block_until_multi(p,terms,3);
        if (eat(p,T_CATCH)) {
            if (at(p,T_IDENT)) { n->u.trystmt.errvar=dup_text(cur(p)); adv(p); }
            static const TokType t2[]={T_FINALLY,T_END};
            n->u.trystmt.catchb = parse_block_until_multi(p,t2,2);
        }
        if (eat(p,T_FINALLY)) {
            static const TokType t3[]={T_END};
            n->u.trystmt.finallyb = parse_block_until_multi(p,t3,1);
        }
        expect(p,T_END,"END");
        finish_line(p);
        return n;
    }
    case T_THROW: {
        adv(p);
        Node *n = mk(S_THROW,line);
        n->u.solo.single = parse_expr(p);
        finish_line(p);
        return n;
    }
    case T_SWITCH: {
        adv(p);
        Node *n = mk(S_SWITCH,line);
        n->u.swtch.subj = parse_expr(p);
        eat(p,T_THEN);
        int cap=8;
        n->u.swtch.cases=malloc(cap*sizeof(Node*));
        n->u.swtch.bodies=malloc(cap*sizeof(Node*));
        n->u.swtch.ncase=0; n->u.swtch.dflt=NULL;
        static const TokType stop[]={T_CASE,T_DEFAULTK,T_END,T_ENDIF};
        /* skip filler */
        skip_nl(p);
        while (!at(p,T_EOF_TOK)) {
            if (at(p,T_END)||at(p,T_ENDIF)) break;
            if (eat(p,T_DEFAULTK)) {
                eat(p,T_COLON);
                static const TokType t2[]={T_CASE,T_DEFAULTK,T_END,T_ENDIF};
                n->u.swtch.dflt = parse_block_until_multi(p,t2,4);
                continue;
            }
            if (eat(p,T_CASE)) {
                Node *v = parse_expr(p);
                eat(p,T_COLON);
                static const TokType t3[]={T_CASE,T_DEFAULTK,T_END,T_ENDIF};
                Node *body = parse_block_until_multi(p,t3,4);
                if (n->u.swtch.ncase==cap){
                    cap*=2;
                    n->u.swtch.cases=realloc(n->u.swtch.cases,cap*sizeof(Node*));
                    n->u.swtch.bodies=realloc(n->u.swtch.bodies,cap*sizeof(Node*));
                }
                n->u.swtch.cases[n->u.swtch.ncase]=v;
                n->u.swtch.bodies[n->u.swtch.ncase]=body;
                n->u.swtch.ncase++;
                continue;
            }
            (void)stop;
            skip_nl(p);
            if (at(p,T_CASE)||at(p,T_DEFAULTK)) continue;
            break;
        }
        eat(p,T_END); eat(p,T_ENDIF);
        finish_line(p);
        return n;
    }
    case T_IMPORT: {
        adv(p);
        Node *n = mk(S_IMPORT,line);
        n->u.imp.mod = dup_text(cur(p));
        adv(p);
        finish_line(p);
        return n;
    }
    case T_REFLECT: {
        adv(p);
        Node *n = mk(S_REFLECT,line);
        n->u.reflect.x = parse_expr(p);
        finish_line(p);
        return n;
    }
    case T_NEW: {
        Node *e = parse_postfix(p);
        Node *n = mk(S_NEW_STMT,line);
        n->u.call.callee = e; n->u.call.args=NULL; n->u.call.nargs=0;
        finish_line(p);
        return n;
    }
    default: {
        /* label? ident ':' */
        if (at(p,T_IDENT) && p->p+1 < p->n && p->t[p->p+1].type==T_COLON) {
            Node *n = mk(S_LABEL,line);
            n->u.ident.name = dup_text(cur(p));
            adv(p); adv(p);
            return n;
        }
        /* assignment or expression */
        size_t save = p->p;
        Node *lhs = parse_postfix(p);
        if (at(p,T_ASSIGN)) {
            adv(p); skip_nl(p);
            Node *rhs = parse_expr(p);
            /* lambda assignment detection is automatic since parse_expr sees LAMBDA */
            Node *n = mk(S_ASSIGN,line);
            n->u.assign.target = lhs; n->u.assign.value = rhs;
            finish_line(p);
            return n;
        }
        (void)save;
        Node *n = mk(S_EXPR,line);
        n->u.call.callee = lhs; n->u.call.args=NULL; n->u.call.nargs=0;
        finish_line(p);
        return n;
    }
    }
}

Node *parse_program(Token *toks, int n) {
    P p = { toks, n, 0 };
    Node *prog = mk(S_BLOCK, 1);
    int cap=64; prog->u.block.stmts=malloc(cap*sizeof(Node*)); prog->u.block.n=0;
    while (1) {
        skip_nl(&p);
        if (at(&p,T_EOF_TOK)) break;
        Node *st = parse_stmt(&p);
        if (prog->u.block.n==cap){cap*=2;prog->u.block.stmts=realloc(prog->u.block.stmts,cap*sizeof(Node*));}
        prog->u.block.stmts[prog->u.block.n++]=st;
    }
    return prog;
}

void node_free(Node *n) {
    if (!n) return;
    free(n); /* simplified: leak-tolerant for bootstrap interpreter */
}
