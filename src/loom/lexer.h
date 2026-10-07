/* lexer.h — token model for Loom */
#ifndef LOOM_LEXER_H
#define LOOM_LEXER_H

#include "value.h"

typedef enum {
    /* literals & identifiers */
    T_INT, T_DOUBLE, T_STR, T_CHAR, T_IDENT,
    /* operators required by spec */
    T_PLUS,      /* + */
    T_MINUS,     /* - */
    T_STAR,      /* * */
    T_SLASH,     /* / */
    T_MOD,       /* MOD */
    T_LPAREN,    /* ( */
    T_RPAREN,    /* ) */
    T_CARET,     /* ^  (power) */
    T_ASSIGN,    /* =  assignment / equality */
    T_NEQ,       /* != */
    T_LE,        /* <= */
    T_GE,        /* >= */
    T_LT,        /* <  (also << shift context) */
    T_GT,        /* >  (also >> shift context) */
    T_AND,       /* AND */
    T_NOT,       /* NOT */
    T_OR,        /* OR */
    T_IS,        /* IS */
    T_XORKW,     /* XOR keyword */
    /* bitwise shifts as explicit tokens too */
    T_SHL,       /* SHL keyword or << */
    T_SHR,       /* SHR keyword or >> */
    /* keywords */
    T_LET, T_DIM, T_IF, T_THEN, T_ELSEIF, T_ELSE, T_ENDIF,
    T_FOR, T_IN, T_TO, T_STEP, T_NEXT,
    T_WHILE, T_WHILEEND, T_DO, T_UNTIL,
    T_EXIT, T_GOTO, T_GOSUB, T_RETURN, T_CALL,
    T_DEF, T_ENDDEF, T_VAR, T_ARGS,
    T_STR_KW, T_INT_KW, T_DOUBLE_KW, T_CHAR_KW, T_BYTE_KW,
    T_CLASS, T_ENDCLASS, T_NEW,
    T_REFLECT, T_LAMBDA, T_IMPORT, T_END,
    T_CONSOLE, T_INPUT,
    T_TRY, T_CATCH, T_FINALLY, T_THROW,
    T_SWITCH, T_CASE, T_DEFAULTK, T_BREAKS,
    /* punctuation */
    T_COMMA, T_SEMI, T_COLON, T_DOT, T_LBRACK, T_RBRACK,
    T_LBRACE, T_RBRACE,
    /* control */
    T_NL, T_EOF_TOK,
} TokType;

typedef struct {
    TokType type;
    char *text;          /* identifier name or raw literal text */
    Value val;           /* decoded literal value */
    int line, col;
} Token;

/* tokenize source string into newly allocated token array; returns count via *out_n */
Token *lex(const char *src, int *out_n);
const char *tok_name(TokType t);

#endif /* LOOM_LEXER_H */
