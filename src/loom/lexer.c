/* lexer.c — Loom tokenizer (case-insensitive keywords) */
#include "lexer.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <math.h>

typedef struct { const char *word; TokType t; } KwEntry;

static const KwEntry k_keywords[] = {
    {"MOD", T_MOD}, {"AND", T_AND}, {"NOT", T_NOT}, {"OR", T_OR},
    {"IS", T_IS}, {"XOR", T_XORKW}, {"SHL", T_SHL}, {"SHR", T_SHR},
    {"LET", T_LET}, {"DIM", T_DIM},
    {"IF", T_IF}, {"THEN", T_THEN}, {"ELSEIF", T_ELSEIF}, {"ELSE", T_ELSE},
    {"ENDIF", T_ENDIF},
    {"FOR", T_FOR}, {"IN", T_IN}, {"TO", T_TO}, {"STEP", T_STEP}, {"NEXT", T_NEXT},
    {"WHILE", T_WHILE}, {"WHILEEND", T_WHILEEND}, {"DO", T_DO}, {"UNTIL", T_UNTIL},
    {"EXIT", T_EXIT}, {"GOTO", T_GOTO}, {"GOSUB", T_GOSUB}, {"RETURN", T_RETURN},
    {"CALL", T_CALL},
    {"DEF", T_DEF}, {"ENDDEF", T_ENDDEF}, {"VAR", T_VAR}, {"ARGS", T_ARGS},
    {"STR", T_STR_KW}, {"INT", T_INT_KW}, {"DOUBLE", T_DOUBLE_KW},
    {"CHAR", T_CHAR_KW}, {"BYTE", T_BYTE_KW},
    {"CLASS", T_CLASS}, {"ENDCLASS", T_ENDCLASS}, {"NEW", T_NEW},
    {"REFLECT", T_REFLECT}, {"LAMBDA", T_LAMBDA}, {"IMPORT", T_IMPORT},
    {"END", T_END},
    {"CONSOLE", T_CONSOLE}, {"INPUT", T_INPUT},
    {"TRY", T_TRY}, {"CATCH", T_CATCH}, {"FINALLY", T_FINALLY}, {"THROW", T_THROW},
    {"SWITCH", T_SWITCH}, {"CASE", T_CASE}, {"DEFAULT", T_DEFAULTK},
    {"BREAK", T_BREAKS},
    {NULL, T_EOF_TOK},
};

static TokType kw_lookup(const char *up) {
    for (int i = 0; k_keywords[i].word; i++)
        if (strcmp(k_keywords[i].word, up) == 0) return k_keywords[i].t;
    return T_IDENT;
}

typedef struct { Token *a; int n, cap; } TokBuf;

static void push(TokBuf *b, TokType t, const char *text, Value v, int line, int col) {
    if (b->n == b->cap) {
        b->cap = b->cap ? b->cap * 2 : 64;
        b->a = realloc(b->a, b->cap * sizeof(Token));
    }
    Token *k = &b->a[b->n++];
    k->type = t; k->text = text ? strdup(text) : NULL;
    k->val = v; k->line = line; k->col = col;
}

Token *lex(const char *src, int *out_n) {
    TokBuf buf = {0};
    int line = 1, i = 0;
    const char *s = src;

    while (1) {
        char c = s[i];
        /* skip spaces/tabs (not newlines) */
        while (c == ' ' || c == '\t' || c == '\r') c = s[++i];
        /* comments: // and REM */
        if (c == '/' && s[i+1] == '/') {
            while (s[i] && s[i] != '\n') i++;
            continue;
        }
        {
            /* REM comment at token start */
            if ((c == 'R' || c == 'r') && tolower(s[i+1])=='e' && tolower(s[i+2])=='m'
                && (isspace((unsigned char)s[i+3]) || s[i+3]=='\0')) {
                while (s[i] && s[i] != '\n') i++;
                continue;
            }
        }
        if (c == '\0') { push(&buf, T_EOF_TOK, NULL, v_null(), line, 0); break; }
        if (c == '\n') {
            /* collapse consecutive newlines */
            if (buf.n == 0 || buf.a[buf.n-1].type != T_NL)
                push(&buf, T_NL, "\\n", v_null(), line, 0);
            line++; i++; continue;
        }

        int col = i;
        /* numbers */
        if (isdigit((unsigned char)c) || (c == '.' && isdigit((unsigned char)s[i+1]))) {
            int start = i; int isd = 0;
            while (isdigit((unsigned char)s[i])) i++;
            if (s[i] == '.') { isd = 1; i++; while (isdigit((unsigned char)s[i])) i++; }
            if (tolower(s[i]) == 'e') {
                int save = i; i++;
                if (s[i]=='+'||s[i]=='-') i++;
                if (isdigit((unsigned char)s[i])) { isd = 1; while (isdigit((unsigned char)s[i])) i++; }
                else i = save;
            }
            char *raw = strndup(s + start, i - start);
            if (isd) push(&buf, T_DOUBLE, raw, v_double(atof(raw)), line, col);
            else     push(&buf, T_INT,   raw, v_int(strtoll(raw, NULL, 10)), line, col);
            free(raw);
            continue;
        }

        /* strings */
        if (c == '"' || c == '\'') {
            char q = c; i++;
            int start = i;
            while (s[i] && s[i] != q) { if (s[i]=='\\') i++; if (s[i]=='\n') line++; i++; }
            char *body = strndup(s + start, i - start);
            /* decode escapes */
            char *outp = malloc(strlen(body)+1); int o = 0;
            for (size_t j = 0; body[j]; j++) {
                if (body[j]=='\\' && body[j+1]) {
                    j++;
                    switch (body[j]) {
                    case 'n': outp[o++]='\n'; break;
                    case 't': outp[o++]='\t'; break;
                    case 'r': outp[o++]='\r'; break;
                    case '\\': outp[o++]='\\'; break;
                    case '"': outp[o++]='"'; break;
                    case '\'': outp[o++]='\''; break;
                    case '0': outp[o++]='\0'; break;
                    default: outp[o++]=body[j];
                    }
                } else outp[o++] = body[j];
            }
            outp[o] = 0;
            push(&buf, T_STR, outp, v_str(outp), line, col);
            free(body); free(outp);
            if (s[i] == q) i++;
            continue;
        }

        /* identifiers / keywords */
        if (isalpha((unsigned char)c) || c == '_') {
            int start = i;
            while (isalnum((unsigned char)s[i]) || s[i]=='_') i++;
            char *word = strndup(s + start, i - start);
            char *up = strdup(word);
            for (char *p = up; *p; p++) *p = (char)toupper((unsigned char)*p);
            TokType t = kw_lookup(up);
            push(&buf, t, word, v_str(word), line, col);
            free(up);
            /* keep `word` alive inside token text: push duplicated it */
            free(word);
            continue;
        }

        /* two-char operators */
        if (c=='!' && s[i+1]=='=') { push(&buf,T_NEQ,"!=",v_null(),line,col); i+=2; continue; }
        if (c=='<' && s[i+1]=='=') { push(&buf,T_LE,"<=",v_null(),line,col); i+=2; continue; }
        if (c=='>' && s[i+1]=='=') { push(&buf,T_GE,">=",v_null(),line,col); i+=2; continue; }
        if (c=='<' && s[i+1]=='<') { push(&buf,T_SHL,"<<",v_null(),line,col); i+=2; continue; }
        if (c=='>' && s[i+1]=='>') { push(&buf,T_SHR,">>",v_null(),line,col); i+=2; continue; }
        if (c=='=' && s[i+1]=='=') { push(&buf,T_ASSIGN,"==",v_null(),line,col); i+=2; continue; }

        /* single chars */
        TokType t = T_EOF_TOK; const char *tx = NULL; char one[2]={c,0};
        switch (c) {
        case '+': t=T_PLUS; tx="+"; break;
        case '-': t=T_MINUS; tx="-"; break;
        case '*': t=T_STAR; tx="*"; break;
        case '/': t=T_SLASH; tx="/"; break;
        case '(': t=T_LPAREN; tx="("; break;
        case ')': t=T_RPAREN; tx=")"; break;
        case '^': t=T_CARET; tx="^"; break;
        case '=': t=T_ASSIGN; tx="="; break;
        case '<': t=T_LT; tx="<"; break;
        case '>': t=T_GT; tx=">"; break;
        case ',': t=T_COMMA; tx=","; break;
        case ';': t=T_SEMI; tx=";"; break;
        case ':': t=T_COLON; tx=":"; break;
        case '.': t=T_DOT; tx="."; break;
        case '[': t=T_LBRACK; tx="["; break;
        case ']': t=T_RBRACK; tx="]"; break;
        case '{': t=T_LBRACE; tx="{"; break;
        case '}': t=T_RBRACE; tx="}"; break;
        default:
            fprintf(stderr, "lexer: unexpected character '%c' at line %d\n", c, line);
            i++; continue;
        }
        push(&buf, t, tx ? tx : one, v_null(), line, col);
        i++;
    }
    *out_n = buf.n;
    return buf.a;
}

const char *tok_name(TokType t) {
    static char b[32];
    snprintf(b, sizeof b, "tok#%d", (int)t);
    return b;
}
