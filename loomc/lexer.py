""" Lexer LOOM v1. """

from __future__ import annotations

from .token import (
    Token, TokenKind, KEYWORDS, CONTINUATION_KINDS
)
from .errors import LoomError


class Lexer:
    def __init__(self, source: str, filename: str = "<input>"):
        self.src = source
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: list[Token] = []
        self.last_significant: TokenKind | None = None

    def tokenize(self) -> list[Token]:
        while not self._at_end():
            self._scan_token()
        if self.tokens and self.tokens[-1].kind != TokenKind.NEWLINE:
            self._emit(TokenKind.NEWLINE, "\n")
        self._emit(TokenKind.EOF, "")
        return self.tokens

    def _at_end(self) -> bool:
        return self.pos >= len(self.src)

    def _peek(self, offset: int = 0) -> str:
        i = self.pos + offset
        if i >= len(self.src):
            return "\0"
        return self.src[i]

    def _advance(self) -> str:
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _match(self, expected: str) -> bool:
        if self._at_end():
            return False
        if self.src[self.pos] != expected:
            return False
        self._advance()
        return True

    def _emit(self, kind: TokenKind, value: str) -> None:
        tok = Token(kind, value, self._start_line, self._start_col)
        self.tokens.append(tok)
        if kind != TokenKind.NEWLINE:
            self.last_significant = kind


    def _scan_token(self) -> None:
        while not self._at_end() and self._peek() in " \t\r":
            self._advance()

        if self._at_end():
            return

        self._start_line = self.line
        self._start_col = self.col

        ch = self._peek()

        if ch == "\n":
            self._advance()
            if self.last_significant not in CONTINUATION_KINDS:
                self._emit(TokenKind.NEWLINE, "\n")
            return

        if ch == "/" and self._peek(1) == "/":
            self._skip_line_comment()
            return

        if ch == "/" and self._peek(1) == "*":
            self._skip_block_comment()
            return

        if ch.isalpha() or ch == "_":
            self._scan_ident()
            return

        if ch.isdigit():
            self._scan_number()
            return

        if ch == '"':
            self._scan_string()
            return

        if ch == "'":
            self._scan_char()
            return

        self._scan_operator()

    def _scan_ident(self) -> None:
        start = self.pos
        while not self._at_end():
            c = self._peek()
            if c.isalnum() or c == "_":
                self._advance()
            else:
                break
        text = self.src[start:self.pos]
        kind = KEYWORDS.get(text, TokenKind.IDENT)
        self._emit(kind, text)
        
    def _scan_number(self) -> None:
        start = self.pos

        # Hex: 0x...
        if self._peek() == "0" and self._peek(1) in ("x", "X"):
            self._advance()  # 0
            self._advance()  # x
            while not self._at_end() and self._peek() in "0123456789abcdefABCDEF_":
                self._advance()
            text = self.src[start:self.pos]
            self._emit(TokenKind.INT_LIT, text)
            return

        # Bin: 0b...
        if self._peek() == "0" and self._peek(1) in ("b", "B"):
            self._advance()
            self._advance()
            while not self._at_end() and self._peek() in "01_":
                self._advance()
            text = self.src[start:self.pos]
            self._emit(TokenKind.INT_LIT, text)
            return

        # Oct: 0o...
        if self._peek() == "0" and self._peek(1) in ("o", "O"):
            self._advance()
            self._advance()
            while not self._at_end() and self._peek() in "01234567_":
                self._advance()
            text = self.src[start:self.pos]
            self._emit(TokenKind.INT_LIT, text)
            return

        # Decimal
        while not self._at_end() and (self._peek().isdigit() or self._peek() == "_"):
            self._advance()

        is_float = False

        if self._peek() == "." and self._peek(1).isdigit():
            is_float = True
            self._advance()  # .
            while not self._at_end() and (self._peek().isdigit() or self._peek() == "_"):
                self._advance()
        
        # eNNN, e+NNN, e-NNN
        if self._peek() in ("e", "E"):
            nxt = self._peek(1)
            if nxt.isdigit() or (nxt in ("+", "-") and self._peek(2).isdigit()):
                is_float = True
                self._advance()
                if self._peek() in ("+", "-"):
                    self._advance()
                while not self._at_end() and self._peek().isdigit():
                    self._advance()

        text = self.src[start:self.pos]
        kind = TokenKind.FLOAT_LIT if is_float else TokenKind.INT_LIT
        self._emit(kind, text)

    def _scan_string(self) -> None:
        self._advance()
        start = self.pos
        out = []
        while not self._at_end() and self._peek() != '"':
            ch = self._peek()
            if ch == "\n":
                raise LoomError(
                    "unterminated string literal",
                    self.filename, self._start_line, self._start_col
                )
            if ch == "\\":
                self._advance()
                out.append(self._read_escape())
            else:
                out.append(self._advance())
        if self._at_end():
            raise LoomError(
                "unterminated string literal",
                self.filename, self._start_line, self._start_col
            )
        self._advance()
        self._emit(TokenKind.STRING_LIT, "".join(out))

    def _scan_char(self) -> None:
        self._advance()  # '
        if self._at_end():
            raise LoomError(
                "unterminated char literal",
                self.filename, self._start_line, self._start_col
            )
        if self._peek() == "\\":
            self._advance()
            ch = self._read_escape()
        else:
            ch = self._advance()
        if self._peek() != "'":
            raise LoomError(
                "unterminated char literal",
                self.filename, self._start_line, self._start_col
            )
        self._advance()  # '
        self._emit(TokenKind.CHAR_LIT, ch)

    def _read_escape(self) -> str:
        if self._at_end():
            raise LoomError(
                "unexpected end of file in escape sequence",
                self.filename, self.line, self.col
            )
        ch = self._advance()
        mapping = {
            "n": "\n", "t": "\t", "r": "\r", "0": "\0",
            "\\": "\\", '"': '"', "'": "'",
        }
        if ch in mapping:
            return mapping[ch]
        if ch == "x":
            # \xNN
            h1 = self._advance()
            h2 = self._advance()
            try:
                return chr(int(h1 + h2, 16))
            except ValueError:
                raise LoomError(
                    f"invalid hex escape: \\x{h1}{h2}",
                    self.filename, self.line, self.col
                )
        raise LoomError(
            f"unknown escape sequence: \\{ch}",
            self.filename, self.line, self.col
        )

    def _skip_line_comment(self) -> None:
        self._advance()
        self._advance()
        while not self._at_end() and self._peek() != "\n":
            self._advance()

    def _skip_block_comment(self) -> None:
        self._advance()
        self._advance()
        while not self._at_end():
            if self._peek() == "*" and self._peek(1) == "/":
                self._advance()
                self._advance()
                return
            self._advance()
        raise LoomError(
            "unterminated block comment",
            self.filename, self._start_line, self._start_col
        )

    def _scan_operator(self) -> None:
        ch = self._advance()

        single = {
            "(": TokenKind.LPAREN,
            ")": TokenKind.RPAREN,
            "{": TokenKind.LBRACE,
            "}": TokenKind.RBRACE,
            "[": TokenKind.LBRACKET,
            "]": TokenKind.RBRACKET,
            ",": TokenKind.COMMA,
            ":": TokenKind.COLON,
            ";": TokenKind.SEMICOLON,
            ".": TokenKind.DOT,
            "#": TokenKind.HASH,
            "@": TokenKind.AT,
            "~": TokenKind.TILDE,
        }

        if ch == "+":
            if self._match("="): self._emit(TokenKind.PLUS_EQ, "+=")
            else:                self._emit(TokenKind.PLUS, "+")
            return
        if ch == "-":
            if self._match("="):  self._emit(TokenKind.MINUS_EQ, "-=")
            elif self._match(">"): self._emit(TokenKind.ARROW, "->")
            else:                  self._emit(TokenKind.MINUS, "-")
            return
        if ch == "*":
            if self._match("="): self._emit(TokenKind.STAR_EQ, "*=")
            else:                self._emit(TokenKind.STAR, "*")
            return
        if ch == "/":
            if self._match("="): self._emit(TokenKind.SLASH_EQ, "/=")
            else:                self._emit(TokenKind.SLASH, "/")
            return
        if ch == "%":
            if self._match("="): self._emit(TokenKind.PERCENT_EQ, "%=")
            else:                self._emit(TokenKind.PERCENT, "%")
            return
        if ch == "&":
            if self._match("&"): self._emit(TokenKind.AND_AND, "&&")
            elif self._match("="): self._emit(TokenKind.AMP_EQ, "&=")
            else:                  self._emit(TokenKind.AMP, "&")
            return
        if ch == "|":
            if self._match("|"): self._emit(TokenKind.OR_OR, "||")
            elif self._match("="): self._emit(TokenKind.PIPE_EQ, "|=")
            else:                  self._emit(TokenKind.PIPE, "|")
            return
        if ch == "^":
            if self._match("="): self._emit(TokenKind.CARET_EQ, "^=")
            else:                self._emit(TokenKind.CARET, "^")
            return
        if ch == "!":
            if self._match("="): self._emit(TokenKind.NEQ, "!=")
            else:                self._emit(TokenKind.BANG, "!")
            return
        if ch == "=":
            if self._match("="): self._emit(TokenKind.EQ_EQ, "==")
            elif self._match(">"): self._emit(TokenKind.FAT_ARROW, "=>")
            else:                  self._emit(TokenKind.EQ, "=")
            return
        if ch == "<":
            if self._match("<"):
                if self._match("="): self._emit(TokenKind.SHL_EQ, "<<=")
                else:                self._emit(TokenKind.SHL, "<<")
            elif self._match("="): self._emit(TokenKind.LE, "<=")
            else:                  self._emit(TokenKind.LT, "<")
            return
        if ch == ">":
            if self._match(">"):
                if self._match("="): self._emit(TokenKind.SHR_EQ, ">>=")
                else:                self._emit(TokenKind.SHR, ">>")
            elif self._match("="): self._emit(TokenKind.GE, ">=")
            else:                  self._emit(TokenKind.GT, ">")
            return

        if ch in single:
            self._emit(single[ch], ch)
            return

        raise LoomError(
            f"unexpected character: {ch!r}",
            self.filename, self._start_line, self._start_col
        )