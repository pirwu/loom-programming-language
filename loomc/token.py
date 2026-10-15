""" Tokens LOOM v1. """

from dataclasses import dataclass
from enum import Enum, auto

class TokenKind(Enum):
    EOF = auto()
    NEWLINE = auto()
    
    INT_LIT = auto()
    FLOAT_LIT = auto()
    STRING_LIT = auto()
    CHAR_LIT = auto()
    TRUE = auto()
    FALSE = auto()
    NULL = auto()
    
    IDENT = auto()
    
    MODULE = auto()
    IMPORT = auto()
    EXPORT = auto()
    FN = auto()
    RET = auto()
    LET = auto()
    CONST = auto()
    STRUCT = auto()
    ENUM = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    LOOP = auto()
    BREAK = auto()
    CONTINUE = auto()
    JMP = auto()
    EXTERN = auto()
    SYSCALL = auto()
    AS = auto()
    SIZEOF = auto()
    MUT = auto()
    
    I8 = auto(); I16 = auto(); I32 = auto(); I64 = auto()
    U8 = auto(); U16 = auto(); U32 = auto(); U64 = auto()
    F32 = auto(); F64 = auto()
    BOOL = auto(); VOID = auto()
    PTR = auto()
    
    PLUS = auto(); MINUS = auto(); STAR = auto(); SLASH = auto(); PERCENT = auto()
    
    AMP = auto(); PIPE = auto(); CARET = auto(); TILDE = auto()
    SHL = auto(); SHR = auto()
    
    AND_AND = auto(); OR_OR = auto(); BANG = auto()
    
    EQ = auto(); EQ_EQ = auto(); NEQ = auto()
    LT = auto(); LE = auto(); GT = auto(); GE = auto()
    
    PLUS_EQ = auto(); MINUS_EQ = auto(); STAR_EQ = auto()
    SLASH_EQ = auto(); PERCENT_EQ = auto()
    AMP_EQ = auto(); PIPE_EQ = auto(); CARET_EQ = auto()
    SHL_EQ = auto(); SHR_EQ = auto()
    
    LPAREN = auto(); RPAREN = auto()
    LBRACE = auto(); RBRACE = auto()
    LBRACKET = auto(); RBRACKET = auto()
    COMMA = auto(); COLON = auto(); SEMICOLON = auto()
    DOT = auto(); ARROW = auto(); FAT_ARROW = auto()
    HASH = auto(); AT = auto()

KEYWORDS: dict[str, TokenKind] = {
    "module":   TokenKind.MODULE,
    "import":   TokenKind.IMPORT,
    "export":   TokenKind.EXPORT,
    "fn":       TokenKind.FN,
    "ret":      TokenKind.RET,
    "let":      TokenKind.LET,
    "const":    TokenKind.CONST,
    "struct":   TokenKind.STRUCT,
    "enum":     TokenKind.ENUM,
    "if":       TokenKind.IF,
    "else":     TokenKind.ELSE,
    "while":    TokenKind.WHILE,
    "loop":     TokenKind.LOOP,
    "break":    TokenKind.BREAK,
    "continue": TokenKind.CONTINUE,
    "jmp":      TokenKind.JMP,
    "extern":   TokenKind.EXTERN,
    "syscall":  TokenKind.SYSCALL,
    "as":       TokenKind.AS,
    "sizeof":   TokenKind.SIZEOF,
    "mut":      TokenKind.MUT,
    
    "true":     TokenKind.TRUE,
    "false":    TokenKind.FALSE,
    "null":     TokenKind.NULL,
    
    "i8":       TokenKind.I8,
    "i16":      TokenKind.I16,
    "i32":      TokenKind.I32,
    "i64":      TokenKind.I64,
    "u8":       TokenKind.U8,
    "u16":      TokenKind.U16,
    "u32":      TokenKind.U32,
    "u64":      TokenKind.U64,
    "f32":      TokenKind.F32,
    "f64":      TokenKind.F64,
    "bool":     TokenKind.BOOL,
    "void":     TokenKind.VOID,
    "ptr":      TokenKind.PTR,
}

CONTINUATION_KINDS: set[TokenKind] = {
    TokenKind.PLUS, TokenKind.MINUS, TokenKind.STAR, TokenKind.SLASH,
    TokenKind.PERCENT,
    TokenKind.AMP, TokenKind.PIPE, TokenKind.CARET, TokenKind.TILDE,
    TokenKind.AND_AND, TokenKind.OR_OR, TokenKind.BANG,
    TokenKind.EQ,
    TokenKind.PLUS_EQ, TokenKind.MINUS_EQ, TokenKind.STAR_EQ, TokenKind.SLASH_EQ,
    TokenKind.PERCENT_EQ, TokenKind.AMP_EQ, TokenKind.PIPE_EQ, TokenKind.CARET_EQ,
    TokenKind.COMMA, TokenKind.DOT, TokenKind.ARROW, TokenKind.FAT_ARROW,
    TokenKind.LPAREN, TokenKind.LBRACKET, TokenKind.COLON, TokenKind.AT,
    TokenKind.AS,
}

@dataclass
class Token:
    kind: TokenKind
    value: str
    line: int
    col: int

    def __repr__(self) -> str:
        return f"Token({self.kind.name}, {self.value!r}, {self.line}:{self.col})"