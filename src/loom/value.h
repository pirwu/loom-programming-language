/* value.h — runtime value model for Loom */
#ifndef LOOM_VALUE_H
#define LOOM_VALUE_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

typedef enum {
    V_NULL = 0,
    V_INT,      /* int64_t, covers BYTE/INT/DOUBLE storage */
    V_DOUBLE,
    V_STR,      /* char* (heap, refcounted) */
    V_BOOL,
    V_CHAR,     /* single codepoint stored as int64 */
    V_ARRAY,
    V_CLASS,    /* class descriptor */
    V_OBJECT,   /* instance */
    V_FUNC,     /* native or user function pointer */
    V_LAMBDA,
} VType;

struct Array;
struct Env;
struct Node;

/* Class descriptor is defined by the interpreter (interp.h) as ClassDef.
 * V_CLASS values carry a pointer to it through this alias. */
typedef struct ClassDesc { int _loom_classdesc_opaque; } ClassDesc;

typedef struct Value {
    VType type;
    union {
        int64_t i;
        double d;
        char *s;
        struct Array *arr;
        struct ClassDesc *cls;
        struct Object *obj;
        struct { void *fn; struct Env *env; struct Node *body; } call;
    } u;
} Value;

typedef struct Array {
    Value *items;
    size_t len, cap;
} Array;

typedef struct Object {
    struct ClassDesc *cls;   /* actually ClassDef* (see interp.h) */
    Value *fields;
    size_t nfields;
} Object;

Value v_null(void);
Value v_int(int64_t x);
Value v_double(double x);
Value v_str(const char *s);          /* copies */
Value v_str_take(char *s);           /* takes ownership */
Value v_bool(bool b);
Value v_char(int64_t cp);

const char *v_to_cstr(Value v);      /* stable textual form (may alloc static buffer) */
double v_as_double(Value v);
int64_t v_as_int(Value v);
bool v_truthy(Value v);
bool v_eq(Value a, Value b);
void v_retain(Value v);
void v_release(Value v);

#endif /* LOOM_VALUE_H */
