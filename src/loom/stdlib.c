/* stdlib.c — Loom standard library.
 *
 * Math / string builtins follow the classic table:
 *   { "ABS", _std_abs }, { "SGN", _std_sgn }, ... { _STD_ID_VAL, _std_val }
 * File library: open/close/read/write/EOF/seek
 * Bitwise/type helpers: BYTE, SHL, SHR, AND, OR, XOR
 */
#include "interp.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <math.h>
#include <time.h>
#include <ctype.h>

#define _STD_ID_VAL "VAL"

/* ---------- small helpers ---------- */

typedef Value (*StdFn)(Interp *, Value *, int);

static double A(Value *a, int i) { return (i < 0 || !a) ? 0 : v_as_double(a[i]); }
static int64_t I(Value *a, int i) { return (i < 0 || !a) ? 0 : v_as_int(a[i]); }
static const char *S(Value *a, int i) { return (i < 0 || !a) ? "" : v_to_cstr(a[i]); }

/* ---------- math section ---------- */

static Value _std_abs(Interp *ip, Value *a, int n)    { (void)ip;
    if (n>0 && a[0].type==V_DOUBLE) return v_double(fabs(a[0].u.d));
    int64_t x = I(a,0); return v_int(x<0?-x:x); }
static Value _std_sgn(Interp *ip, Value *a, int n)    { (void)ip;(void)n;
    double x = A(a,0); return v_int(x>0?1:(x<0?-1:0)); }
static Value _std_sqr(Interp *ip, Value *a, int n)    { (void)ip;(void)n;
    return v_double(sqrt(A(a,0))); }
static Value _std_floor(Interp *ip, Value *a, int n)  { (void)ip;(void)n;
    return v_int((int64_t)floor(A(a,0))); }
static Value _std_ceil(Interp *ip, Value *a, int n)   { (void)ip;(void)n;
    return v_int((int64_t)ceil(A(a,0))); }
static Value _std_fix(Interp *ip, Value *a, int n)    { (void)ip;(void)n;
    return v_int((int64_t)trunc(A(a,0))); }
static Value _std_round(Interp *ip, Value *a, int n)  { (void)ip;
    double x = A(a,0);
    if (n>=2) { double m = pow(10.0,(double)I(a,1)); return v_double(round(x*m)/m); }
    return v_int(llround(x)); }
static unsigned long g_seed_state = 88172645463325252ULL;
static Value _std_srnd(Interp *ip, Value *a, int n)   { (void)ip;(void)n;
    g_seed_state = (unsigned long)I(a,0) * 2862933555777941757ULL + 3037000493ULL;
    /* prime the generator */
    for (int i=0;i<10;i++) { g_seed_state ^= g_seed_state<<13; g_seed_state ^= g_seed_state>>7; g_seed_state ^= g_seed_state<<17; }
    return v_null(); }
static uint64_t xorshift64(void) {
    uint64_t x = g_seed_state;
    x ^= x << 13; x ^= x >> 7; x ^= x << 17;
    g_seed_state = x;
    return x;
}
static Value _std_rnd(Interp *ip, Value *a, int n)    { (void)ip;
    double r = (double)(xorshift64() >> 11) / 9007199254740992.0;
    if (n>=1) { int64_t hi = I(a,0); return v_int((int64_t)(r*(double)hi)+1); }
    return v_double(r); }
static Value _std_sin(Interp *ip, Value *a, int n)  { (void)ip;(void)n; return v_double(sin(A(a,0))); }
static Value _std_cos(Interp *ip, Value *a, int n)  { (void)ip;(void)n; return v_double(cos(A(a,0))); }
static Value _std_tan(Interp *ip, Value *a, int n)  { (void)ip;(void)n; return v_double(tan(A(a,0))); }
static Value _std_asin(Interp *ip, Value *a, int n) { (void)ip;(void)n; return v_double(asin(A(a,0))); }
static Value _std_acos(Interp *ip, Value *a, int n) { (void)ip;(void)n; return v_double(acos(A(a,0))); }
static Value _std_atan(Interp *ip, Value *a, int n) { (void)ip;
    if (n>=2) return v_double(atan2(A(a,0),A(a,1)));
    return v_double(atan(A(a,0))); }
static Value _std_exp(Interp *ip, Value *a, int n)  { (void)ip;(void)n; return v_double(exp(A(a,0))); }
static Value _std_log(Interp *ip, Value *a, int n)  { (void)ip;
    if (n>=2) return v_double(log(A(a,1))/log(A(a,0))); /* LOG(base,x) like old BASICs */
    return v_double(log(A(a,0))); }

/* ---------- string section ---------- */

static Value _std_asc(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    const char *s = S(a,0);
    return v_int(s && s[0] ? (unsigned char)s[0] : 0); }
static Value _std_chr(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    char b[2] = { (char)I(a,0), 0 };
    return v_str(b); }
static Value _std_left(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    const char *s = S(a,0); long k = I(a,1); size_t L=strlen(s);
    if (k<0) k=0;
    if ((size_t)k>L) k=(long)L;
    return v_str_take(strndup(s,(size_t)k)); }
static Value _std_right(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    const char *s = S(a,0); long k = I(a,1); size_t L=strlen(s);
    if (k<0) k=0;
    if ((size_t)k>L) k=(long)L;
    return v_str(s + (L-(size_t)k)); }
static Value _std_mid(Interp *ip, Value *a, int n) { (void)ip;
    const char *s = S(a,0);
    long p = I(a,1); if (p<1) p=1;
    size_t L = strlen(s);
    if ((size_t)p > L) return v_str("");
    long cnt = (n>=3) ? I(a,2) : (long)(L - (size_t)p + 1);
    if (cnt<0) cnt=0;
    if ((size_t)((size_t)p-1+ (size_t)cnt) > L) cnt = (long)(L-(size_t)p+1);
    return v_str_take(strndup(s+(p-1),(size_t)cnt)); }
static Value _std_str(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    return v_str(v_to_cstr(a[0])); }
static Value _std_val(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    const char *s = S(a,0);
    char *end;
    double d = strtod(s, &end);
    if (end != s && strchr(s,'.')) return v_double(d);
    /* integer when no dot present */
    if (!strchr(s,'.')) return v_int((int64_t)strtoll(s,NULL,10));
    return v_double(d); }

/* ---------- bitwise / byte section ---------- */

static Value _std_byte(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    return v_int(I(a,0) & 0xFF); }
static Value _std_shl(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    return v_int((uint64_t)(I(a,0)&0xFFFFFFFFFFFFFFFFULL) << (I(a,1)&63)); }
static Value _std_shr(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    return v_int((int64_t)((uint64_t)I(a,0) >> (I(a,1)&63))); }
static Value _std_band(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    return v_int(I(a,0) & I(a,1)); }
static Value _std_bor(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    return v_int(I(a,0) | I(a,1)); }
static Value _std_bxor(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    return v_int(I(a,0) ^ I(a,1)); }

/* ---------- extra string/misc ---------- */

static Value _std_len(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    if (n>0 && a[0].type==V_ARRAY) return v_int((int64_t)a[0].u.arr->len);
    return v_int((int64_t)strlen(S(a,0))); }
static Value _std_ucase(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    char *s = strdup(S(a,0)); for(char *p=s;*p;p++) *p=(char)toupper((unsigned char)*p);
    return v_str_take(s); }
static Value _std_lcase(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    char *s = strdup(S(a,0)); for(char *p=s;*p;p++) *p=(char)tolower((unsigned char)*p);
    return v_str_take(s); }
static Value _std_instr(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    const char *h = S(a,0), *h2 = strstr(h, S(a,1));
    return v_int(h2 ? (int64_t)(h2-h+1) : 0); }
static Value _std_trim(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    const char *s = S(a,0); while(*s==' ') s++;
    size_t L=strlen(s); while(L && s[L-1]==' ') L--;
    return v_str_take(strndup(s,L)); }
static Value _std_type(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    switch (a[0].type) {
    case V_INT: return v_str("INT");
    case V_DOUBLE: return v_str("DOUBLE");
    case V_STR: return v_str("STR");
    case V_BOOL: return v_str("BOOL");
    case V_CHAR: return v_str("CHAR");
    case V_ARRAY: return v_str("ARRAY");
    case V_CLASS: return v_str("CLASS");
    case V_OBJECT: return v_str("OBJECT");
    default: return v_str("NULL");
    } }
static Value _std_input_line(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    char buf[4096]; if(!fgets(buf,sizeof buf,stdin)) buf[0]=0;
    size_t L=strlen(buf); if(L&&buf[L-1]=='\n') buf[--L]=0;
    return v_str(buf); }

/* ---------- file library: open close read write EOF seek ---------- */

typedef struct FEnt {
    int handle;
    FILE *fp;
    struct FEnt *next;
} FEnt;

static FEnt *g_files = NULL;
static int g_next_handle = 1;

static FEnt *fent_find(int h) {
    for (FEnt *f = g_files; f; f = f->next) if (f->handle == h) return f;
    return NULL;
}

static Value _fl_open(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    const char *path = S(a,0);
    const char *mode = (n>=2) ? S(a,1) : "r";
    const char *fmode = "r";
    if      (!strcasecmp(mode,"input")  || !strcmp(mode,"r")) fmode="r";
    else if (!strcasecmp(mode,"output") || !strcmp(mode,"w")) fmode="w";
    else if (!strcasecmp(mode,"append") || !strcmp(mode,"a")) fmode="a";
    else if (!strcmp(mode,"r+")) fmode="r+";
    else if (!strcmp(mode,"w+")) fmode="w+";
    FILE *fp = fopen(path, fmode);
    if (!fp) return v_int(-1);
    FEnt *f = calloc(1,sizeof(FEnt));
    f->handle = g_next_handle++;
    f->fp = fp;
    f->next = g_files;
    g_files = f;
    return v_int(f->handle);
}

static Value _fl_close(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    int h = (int)I(a,0);
    FEnt **pp = &g_files;
    while (*pp) {
        if ((*pp)->handle == h) {
            fclose((*pp)->fp);
            FEnt *d = *pp; *pp = d->next; free(d);
            return v_bool(true);
        }
        pp = &(*pp)->next;
    }
    return v_bool(false);
}

static Value _fl_read(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    int h = (int)I(a,0);
    FEnt *f = fent_find(h);
    if (!f) return v_str("");
    if (n >= 2) { /* READ #h, LEN$ -> read exact number of chars */
        long cnt = I(a,1);
        char *buf = malloc((size_t)cnt+1);
        size_t got = fread(buf,1,(size_t)cnt,f->fp);
        buf[got]=0;
        return v_str_take(buf);
    }
    char buf[4096];
    if (!fgets(buf,sizeof buf,f->fp)) return v_str("");
    size_t L=strlen(buf); if(L&&buf[L-1]=='\n') buf[--L]=0;
    return v_str(buf);
}

static Value _fl_write(Interp *ip, Value *a, int n) { (void)ip;
    if (n < 2) return v_bool(false);
    int h = (int)I(a,0);
    FEnt *f = fent_find(h);
    if (!f) return v_bool(false);
    fputs(v_to_cstr(a[1]), f->fp);
    fflush(f->fp);
    return v_bool(true);
}

static Value _fl_eof(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    int h = (int)I(a,0);
    FEnt *f = fent_find(h);
    if (!f) return v_bool(true);
    int c = fgetc(f->fp);
    if (c == EOF) return v_bool(true);
    ungetc(c, f->fp);
    return v_bool(false);
}

static Value _fl_seek(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    int h = (int)I(a,0);
    long pos = I(a,1);
    FEnt *f = fent_find(h);
    if (!f) return v_int(-1);
    return v_int(fseek(f->fp, pos, SEEK_SET) == 0 ? ftell(f->fp) : -1);
}

static Value _fl_lof(Interp *ip, Value *a, int n) { (void)ip;(void)n;
    int h = (int)I(a,0);
    FEnt *f = fent_find(h);
    if (!f) return v_int(-1);
    long cur = ftell(f->fp);
    fseek(f->fp,0,SEEK_END);
    long sz = ftell(f->fp);
    fseek(f->fp,cur,SEEK_SET);
    return v_int(sz);
}

/* ---------- registration table (classic style) ---------- */

static struct { const char *id; StdFn fn; } std_table[] = {
    { "ABS",   _std_abs },
    { "SGN",   _std_sgn },
    { "SQR",   _std_sqr },
    { "FLOOR", _std_floor },
    { "CEIL",  _std_ceil },
    { "FIX",   _std_fix },
    { "ROUND", _std_round },
    { "SRND",  _std_srnd },
    { "RND",   _std_rnd },
    { "SIN",   _std_sin },
    { "COS",   _std_cos },
    { "TAN",   _std_tan },
    { "ASIN",  _std_asin },
    { "ACOS",  _std_acos },
    { "ATAN",  _std_atan },
    { "EXP",   _std_exp },
    { "LOG",   _std_log },

    { "ASC",   _std_asc },
    { "CHR",   _std_chr },
    { "LEFT",  _std_left },
    { "MID",   _std_mid },
    { "RIGHT", _std_right },
    { "STR",   _std_str },
    { _STD_ID_VAL, _std_val },

    /* bitwise / byte extensions */
    { "BYTE",  _std_byte },
    { "SHL",   _std_shl },
    { "SHR",   _std_shr },
    { "AND",   _std_band },
    { "OR",    _std_bor },
    { "XOR",   _std_bxor },

    /* misc strings */
    { "LEN",   _std_len },
    { "UCASE", _std_ucase },
    { "LCASE", _std_lcase },
    { "INSTR", _std_instr },
    { "TRIM",  _std_trim },
    { "TYPE",  _std_type },
    { "READLINE", _std_input_line },

    /* file library */
    { "OPEN",  _fl_open },
    { "CLOSE", _fl_close },
    { "READ",  _fl_read },
    { "WRITE", _fl_write },
    { "EOF",   _fl_eof },
    { "SEEK",  _fl_seek },
    { "LOF",   _fl_lof },
    { NULL, NULL },
};


void stdlib_register(Interp *ip) {
    /* seed RNG deterministically unless SRND called */
    g_seed_state ^= (unsigned long)time(NULL);
    for (int i = 0; std_table[i].id; i++)
        register_native(ip, std_table[i].id, std_table[i].fn);
}
