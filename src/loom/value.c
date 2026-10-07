/* value.c — runtime value helpers */
#include "value.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

Value v_null(void)            { Value v = {V_NULL, {0}}; return v; }
Value v_int(int64_t x)        { Value v = {V_INT, {0}}; v.u.i = x; return v; }
Value v_double(double x)      { Value v = {V_DOUBLE, {0}}; v.u.d = x; return v; }
Value v_bool(bool b)          { Value v = {V_BOOL, {0}}; v.u.i = b ? 1 : 0; return v; }
Value v_char(int64_t cp)      { Value v = {V_CHAR, {0}}; v.u.i = cp; return v; }

Value v_str(const char *s) {
    Value v = {V_STR, {0}};
    v.u.s = strdup(s ? s : "");
    return v;
}

Value v_str_take(char *s) {
    Value v = {V_STR, {0}};
    v.u.s = s ? s : strdup("");
    return v;
}

double v_as_double(Value v) {
    switch (v.type) {
    case V_DOUBLE: return v.u.d;
    case V_INT:
    case V_CHAR:
    case V_BOOL: return (double)v.u.i;
    case V_STR:  return atof(v.u.s);
    default: return 0.0/0.0;
    }
}

int64_t v_as_int(Value v) {
    switch (v.type) {
    case V_INT:
    case V_CHAR:
    case V_BOOL: return v.u.i;
    case V_DOUBLE: return (int64_t)llround(v.u.d);
    case V_STR:  return (int64_t)strtoll(v.u.s, NULL, 10);
    default: return 0;
    }
}

bool v_truthy(Value v) {
    switch (v.type) {
    case V_NULL: return false;
    case V_BOOL: return v.u.i != 0;
    case V_INT: case V_CHAR: return v.u.i != 0;
    case V_DOUBLE: return v.u.d != 0.0;
    case V_STR: return v.u.s && v.u.s[0];
    default: return true;
    }
}

static char g_buf[4096];

const char *v_to_cstr(Value v) {
    switch (v.type) {
    case V_NULL: return "NULL";
    case V_BOOL: return v.u.i ? "TRUE" : "FALSE";
    case V_INT: case V_CHAR:
        snprintf(g_buf, sizeof g_buf, "%lld", (long long)v.u.i);
        return g_buf;
    case V_DOUBLE:
        if (v.u.d == floor(v.u.d) && fabs(v.u.d) < 1e15)
            snprintf(g_buf, sizeof g_buf, "%lld", (long long)v.u.d);
        else
            snprintf(g_buf, sizeof g_buf, "%g", v.u.d);
        return g_buf;
    case V_STR: return v.u.s ? v.u.s : "";
    case V_ARRAY: return "<ARRAY>";
    case V_CLASS: return "<CLASS>";
    case V_OBJECT: return "<OBJECT>";
    default: return "<FUNC>";
    }
}

bool v_eq(Value a, Value b) {
    if (a.type == V_STR || b.type == V_STR) {
        const char *x = v_to_cstr(a), *y = v_to_cstr(b);
        return strcmp(x, y) == 0;
    }
    if (a.type == V_NULL || b.type == V_NULL) return a.type == b.type;
    if (a.type == V_DOUBLE || b.type == V_DOUBLE)
        return v_as_double(a) == v_as_double(b);
    return v_as_int(a) == v_as_int(b);
}

void v_retain(Value v) { (void)v; } /* simple arena-less model: no-op for now */

void v_release(Value v) {
    if (v.type == V_STR) free(v.u.s);
}
