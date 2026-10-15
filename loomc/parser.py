"""
Parser LOOM v1.
"""

from __future__ import annotations

from .token import Token, TokenKind
from .lexer import Lexer
from .errors import LoomError
from . import ast as A

BINOP_PRECEDENCE: dict[TokenKind, int] = {
    TokenKind.OR_OR:   1,
    TokenKind.AND_AND: 2,
    TokenKind.PIPE:    3,
    TokenKind.CARET:   4,
    TokenKind.AMP:     5,
    TokenKind.EQ_EQ:   6,
    TokenKind.NEQ:     6,
    TokenKind.LT:      7,
    TokenKind.LE:      7,
    TokenKind.GT:      7,
    TokenKind.GE:      7,
    TokenKind.SHL:     8,
    TokenKind.SHR:     8,
    TokenKind.PLUS:    9,
    TokenKind.MINUS:   9,
    TokenKind.STAR:   10,
    TokenKind.SLASH:  10,
    TokenKind.PERCENT: 10,
}

BINOP_TEXT: dict[TokenKind, str] = {
    TokenKind.OR_OR:   "||",
    TokenKind.AND_AND: "&&",
    TokenKind.PIPE:    "|",
    TokenKind.CARET:   "^",
    TokenKind.AMP:     "&",
    TokenKind.EQ_EQ:   "==",
    TokenKind.NEQ:     "!=",
    TokenKind.LT:      "<",
    TokenKind.LE:      "<=",
    TokenKind.GT:      ">",
    TokenKind.GE:      ">=",
    TokenKind.SHL:     "<<",
    TokenKind.SHR:     ">>",
    TokenKind.PLUS:    "+",
    TokenKind.MINUS:   "-",
    TokenKind.STAR:    "*",
    TokenKind.SLASH:   "/",
    TokenKind.PERCENT: "%",
}

COMPOUND_ASSIGN: dict[TokenKind, str] = {
    TokenKind.PLUS_EQ:    "+=",
    TokenKind.MINUS_EQ:   "-=",
    TokenKind.STAR_EQ:    "*=",
    TokenKind.SLASH_EQ:   "/=",
    TokenKind.PERCENT_EQ: "%=",
    TokenKind.AMP_EQ:     "&=",
    TokenKind.PIPE_EQ:    "|=",
    TokenKind.CARET_EQ:   "^=",
    TokenKind.SHL_EQ:     "<<=",
    TokenKind.SHR_EQ:     ">>=",
}

PRIMITIVE_TYPES: dict[TokenKind, str] = {
    TokenKind.I8:   "i8",
    TokenKind.I16:  "i16",
    TokenKind.I32:  "i32",
    TokenKind.I64:  "i64",
    TokenKind.U8:   "u8",
    TokenKind.U16:  "u16",
    TokenKind.U32:  "u32",
    TokenKind.U64:  "u64",
    TokenKind.F32:  "f32",
    TokenKind.F64:  "f64",
    TokenKind.BOOL: "bool",
    TokenKind.VOID: "void",
}


class Parser:
    def __init__(self, tokens: list[Token], filename: str = "<input>"):
        self.tokens = tokens
        self.filename = filename
        self.pos = 0

    def _peek(self, offset: int = 0) -> Token:
        i = self.pos + offset
        if i >= len(self.tokens):
            return self.tokens[-1]  # EOF
        return self.tokens[i]

    def _check(self, kind: TokenKind) -> bool:
        return self._peek().kind == kind

    def _check_any(self, kinds: tuple[TokenKind, ...]) -> bool:
        return self._peek().kind in kinds

    def _advance(self) -> Token:
        tok = self._peek()
        if not self._check(TokenKind.EOF):
            self.pos += 1
        return tok

    def _match(self, kind: TokenKind) -> bool:
        if self._check(kind):
            self._advance()
            return True
        return False

    def _expect(self, kind: TokenKind, what: str = "") -> Token:
        if self._check(kind):
            return self._advance()
        tok = self._peek()
        expected = what or kind.name
        raise LoomError(
            f"expected {expected}, got {tok.kind.name} {tok.value!r}",
            self.filename, tok.line, tok.col
        )

    def _skip_newlines(self) -> None:
        while self._check(TokenKind.NEWLINE):
            self._advance()

    def _skip_separators(self) -> None:
        while self._check_any((TokenKind.NEWLINE, TokenKind.SEMICOLON)):
            self._advance()

    def parse_module(self) -> A.Module:
        self._skip_separators()

        mod_tok = self._expect(TokenKind.MODULE, "module")
        name_tok = self._expect(TokenKind.IDENT, "module name")
        module = A.Module(line=mod_tok.line, col=mod_tok.col, name=name_tok.value)

        self._skip_separators()

        while self._check(TokenKind.IMPORT):
            self._advance()
            imp_name = self._expect(TokenKind.IDENT, "import name")
            module.imports.append(imp_name.value)
            self._skip_separators()

        while not self._check(TokenKind.EOF):
            self._skip_separators()
            if self._check(TokenKind.EOF):
                break
            decl = self._parse_toplevel()
            if decl is not None:
                module.decls.append(decl)

        return module

    def _parse_toplevel(self) -> A.Node | None:
        attrs: list[str] = []
        while self._check(TokenKind.AT):
            self._advance()
            attr_name = self._expect(TokenKind.IDENT, "attribute name")
            attrs.append(attr_name.value)
            self._skip_newlines()

        is_export = self._match(TokenKind.EXPORT)

        self._skip_newlines()

        tok = self._peek()

        if tok.kind == TokenKind.FN:
            return self._parse_fn(is_export, attrs)
        if tok.kind == TokenKind.EXTERN:
            return self._parse_extern_fn(attrs)
        if tok.kind == TokenKind.STRUCT:
            return self._parse_struct(is_export)
        if tok.kind == TokenKind.ENUM:
            return self._parse_enum(is_export)
        if tok.kind == TokenKind.CONST:
            return self._parse_const(is_export)
        if tok.kind == TokenKind.LET:
            return self._parse_global_let(is_export)

        raise LoomError(
            f"unexpected token at top level: {tok.kind.name} {tok.value!r}",
            self.filename, tok.line, tok.col
        )

    def _parse_fn(self, is_export: bool, attrs: list[str]) -> A.FnDecl:
        fn_tok = self._expect(TokenKind.FN)
        name_tok = self._expect(TokenKind.IDENT, "function name")
        fn = A.FnDecl(
            line=fn_tok.line, col=fn_tok.col,
            name=name_tok.value,
            is_export=is_export,
            attrs=attrs,
        )

        self._expect(TokenKind.LPAREN)
        if not self._check(TokenKind.RPAREN):
            while True:
                p_name = self._expect(TokenKind.IDENT, "parameter name")
                self._expect(TokenKind.COLON)
                p_type = self._parse_type()
                fn.params.append(A.FnParam(line=p_name.line, col=p_name.col,
                                           name=p_name.value, type=p_type))
                if not self._match(TokenKind.COMMA):
                    break
        self._expect(TokenKind.RPAREN)

        if self._match(TokenKind.ARROW):
            fn.ret_type = self._parse_type()

        self._skip_newlines()
        fn.body = self._parse_block()
        return fn

    def _parse_extern_fn(self, attrs: list[str]) -> A.FnDecl:
        ext_tok = self._expect(TokenKind.EXTERN)
        self._expect(TokenKind.FN)
        name_tok = self._expect(TokenKind.IDENT, "function name")
        fn = A.FnDecl(
            line=ext_tok.line, col=ext_tok.col,
            name=name_tok.value,
            is_extern=True,
            attrs=attrs,
        )

        self._expect(TokenKind.LPAREN)
        if not self._check(TokenKind.RPAREN):
            while True:
                p_name = self._expect(TokenKind.IDENT, "parameter name")
                self._expect(TokenKind.COLON)
                p_type = self._parse_type()
                fn.params.append(A.FnParam(line=p_name.line, col=p_name.col,
                                           name=p_name.value, type=p_type))
                if not self._match(TokenKind.COMMA):
                    break
        self._expect(TokenKind.RPAREN)

        if self._match(TokenKind.ARROW):
            fn.ret_type = self._parse_type()

        self._match(TokenKind.SEMICOLON)
        return fn

    def _parse_type(self) -> A.TypeRef:
        tok = self._peek()

        if tok.kind == TokenKind.LBRACKET:
            self._advance()
            size_tok = self._expect(TokenKind.INT_LIT, "array size")
            n = self._parse_int_literal(size_tok.value)
            self._expect(TokenKind.RBRACKET)
            inner = self._parse_type()
            return A.TypeRef(line=tok.line, col=tok.col, name="array", inner=inner, array_len=n)

        if tok.kind == TokenKind.PTR:
            self._advance()
            self._expect(TokenKind.LT)
            inner = self._parse_type()
            self._expect(TokenKind.GT)
            return A.TypeRef(line=tok.line, col=tok.col, name="ptr", inner=inner)

        if tok.kind in PRIMITIVE_TYPES:
            self._advance()
            return A.TypeRef(line=tok.line, col=tok.col,
                             name=PRIMITIVE_TYPES[tok.kind])

        if tok.kind == TokenKind.IDENT:
            self._advance()
            return A.TypeRef(line=tok.line, col=tok.col, name=tok.value)

        raise LoomError(
            f"expected type, got {tok.kind.name} {tok.value!r}",
            self.filename, tok.line, tok.col
        )

    def _parse_struct(self, is_export: bool) -> A.StructDecl:
        st_tok = self._expect(TokenKind.STRUCT)
        name_tok = self._expect(TokenKind.IDENT, "struct name")
        self._skip_newlines()
        self._expect(TokenKind.LBRACE)
        self._skip_separators()

        s = A.StructDecl(line=st_tok.line, col=st_tok.col,
                         name=name_tok.value, is_export=is_export)

        while not self._check(TokenKind.RBRACE):
            self._skip_separators()
            if self._check(TokenKind.RBRACE):
                break
            f_name = self._expect(TokenKind.IDENT, "field name")
            self._expect(TokenKind.COLON)
            f_type = self._parse_type()
            s.fields.append(A.StructField(line=f_name.line, col=f_name.col,
                                          name=f_name.value, type=f_type))
            self._skip_separators()

        self._expect(TokenKind.RBRACE)
        return s

    def _parse_enum(self, is_export: bool) -> A.EnumDecl:
        en_tok = self._expect(TokenKind.ENUM)
        name_tok = self._expect(TokenKind.IDENT, "enum name")
        self._skip_newlines()
        self._expect(TokenKind.LBRACE)
        self._skip_separators()

        e = A.EnumDecl(line=en_tok.line, col=en_tok.col,
                       name=name_tok.value, is_export=is_export)

        next_val = 0
        while not self._check(TokenKind.RBRACE):
            self._skip_separators()
            if self._check(TokenKind.RBRACE):
                break
            v_name = self._expect(TokenKind.IDENT, "enum variant")
            explicit: int | None = None
            if self._match(TokenKind.EQ):
                val_tok = self._expect(TokenKind.INT_LIT, "integer")
                explicit = self._parse_int_literal(val_tok.value)
            if explicit is not None:
                next_val = explicit
            e.variants.append(A.EnumVariant(line=v_name.line, col=v_name.col,
                                            name=v_name.value, value=next_val))
            next_val += 1
            self._skip_separators()

        self._expect(TokenKind.RBRACE)
        return e

    def _parse_const(self, is_export: bool) -> A.ConstDecl:
        c_tok = self._expect(TokenKind.CONST)
        name_tok = self._expect(TokenKind.IDENT, "constant name")
        c = A.ConstDecl(line=c_tok.line, col=c_tok.col,
                        name=name_tok.value, is_export=is_export)
        if self._match(TokenKind.COLON):
            c.type = self._parse_type()
        self._expect(TokenKind.EQ)
        c.value = self._parse_expr()
        return c

    def _parse_global_let(self, is_export: bool) -> A.GlobalVarDecl:
        l_tok = self._expect(TokenKind.LET)
        name_tok = self._expect(TokenKind.IDENT, "variable name")
        g = A.GlobalVarDecl(line=l_tok.line, col=l_tok.col,
                            name=name_tok.value, is_export=is_export)
        self._expect(TokenKind.COLON)
        g.type = self._parse_type()
        if self._match(TokenKind.EQ):
            g.value = self._parse_expr()
        return g

    def _parse_block(self) -> A.Block:
        lb = self._expect(TokenKind.LBRACE)
        block = A.Block(line=lb.line, col=lb.col)
        self._skip_separators()
        while not self._check(TokenKind.RBRACE) and not self._check(TokenKind.EOF):
            stmt = self._parse_stmt()
            if stmt is not None:
                block.stmts.append(stmt)
            self._skip_separators()
        self._expect(TokenKind.RBRACE)
        return block

    def _parse_stmt(self) -> A.Node | None:
        self._skip_separators()
        if self._check_any((TokenKind.RBRACE, TokenKind.EOF)):
            return None

        tok = self._peek()
        
        # ret
        if tok.kind == TokenKind.RET:
            self._advance()
            if self._check_any((TokenKind.NEWLINE, TokenKind.SEMICOLON,
                                TokenKind.RBRACE)):
                return A.Ret(line=tok.line, col=tok.col, value=None)
            val = self._parse_expr()
            return A.Ret(line=tok.line, col=tok.col, value=val)

        # if
        if tok.kind == TokenKind.IF:
            return self._parse_if()

        # while
        if tok.kind == TokenKind.WHILE:
            return self._parse_while()

        # loop
        if tok.kind == TokenKind.LOOP:
            self._advance()
            self._skip_newlines()
            body = self._parse_block()
            return A.Loop(line=tok.line, col=tok.col, body=body)

        # break / continue
        if tok.kind == TokenKind.BREAK:
            self._advance()
            return A.Break(line=tok.line, col=tok.col)
        if tok.kind == TokenKind.CONTINUE:
            self._advance()
            return A.Continue(line=tok.line, col=tok.col)

        # jmp label
        if tok.kind == TokenKind.JMP:
            self._advance()
            label = self._expect(TokenKind.IDENT, "label name")
            return A.Jmp(line=tok.line, col=tok.col, label=label.value)

        if tok.kind == TokenKind.IDENT and self._peek(1).kind == TokenKind.COLON:
            after_colon = self._peek(2)
            if after_colon.kind == TokenKind.NEWLINE:
                self._advance()
                self._advance()
                return A.Label(line=tok.line, col=tok.col, name=tok.value)

        # IDENT COLON type [= expr]
        if tok.kind == TokenKind.IDENT and self._peek(1).kind == TokenKind.COLON:
            self._advance()
            name_tok = tok
            self._advance()
            vtype = self._parse_type()
            v = A.VarDecl(line=name_tok.line, col=name_tok.col,
                          name=name_tok.value, type=vtype, value=None)
            if self._match(TokenKind.EQ):
                v.value = self._parse_expr()
            return v

        return self._parse_expr_or_assign()

    def _parse_if(self) -> A.If:
        if_tok = self._expect(TokenKind.IF)
        cond = self._parse_expr()
        self._skip_newlines()
        then_block = self._parse_block()
        else_block: A.Block | None = None

        self._skip_separators()
        if self._match(TokenKind.ELSE):
            self._skip_newlines()
            if self._check(TokenKind.IF):
                nested = self._parse_if()
                else_block = A.Block(line=nested.line, col=nested.col,
                                     stmts=[nested])
            else:
                else_block = self._parse_block()

        return A.If(line=if_tok.line, col=if_tok.col, cond=cond,
                    then_block=then_block, else_block=else_block)

    def _parse_while(self) -> A.While:
        w_tok = self._expect(TokenKind.WHILE)
        cond = self._parse_expr()
        self._skip_newlines()
        body = self._parse_block()
        return A.While(line=w_tok.line, col=w_tok.col, cond=cond, body=body)

    def _parse_expr_or_assign(self) -> A.Node:
        start_tok = self._peek()
        expr = self._parse_expr()

        if self._check(TokenKind.EQ) or self._check_any(tuple(COMPOUND_ASSIGN.keys())):
            if not self._is_lvalue(expr):
                raise LoomError(
                    "invalid assignment target",
                    self.filename, start_tok.line, start_tok.col
                )

            if self._check(TokenKind.EQ):
                self._advance()
                value = self._parse_expr()
                return A.Assign(line=start_tok.line, col=start_tok.col,
                                target=expr, op="=", value=value)

            op_tok = self._advance()
            op = COMPOUND_ASSIGN[op_tok.kind]
            value = self._parse_expr()
            return A.Assign(line=start_tok.line, col=start_tok.col,
                            target=expr, op=op, value=value)

        return A.ExprStmt(line=start_tok.line, col=start_tok.col, expr=expr)

    @staticmethod
    def _is_lvalue(node: A.Node) -> bool:
        if isinstance(node, A.Ident):
            return True
        if isinstance(node, A.UnOp) and node.op == "*":
            return True
        if isinstance(node, A.MemberAccess):
            return True
        if isinstance(node, A.Index):
            return True
        return False

    def _parse_expr(self, min_prec: int = 0) -> A.Node:
        left = self._parse_unary()

        while True:
            tok = self._peek()
            prec = BINOP_PRECEDENCE.get(tok.kind)
            if prec is None or prec < min_prec:
                break
            self._advance()
            right = self._parse_expr(prec + 1)
            left = A.BinOp(line=left.line, col=left.col,
                           op=BINOP_TEXT[tok.kind], left=left, right=right)

        return left

    def _parse_unary(self) -> A.Node:
        tok = self._peek()

        if tok.kind == TokenKind.MINUS:
            self._advance()
            operand = self._parse_unary()
            return A.UnOp(line=tok.line, col=tok.col, op="-", operand=operand)

        if tok.kind == TokenKind.BANG:
            self._advance()
            operand = self._parse_unary()
            return A.UnOp(line=tok.line, col=tok.col, op="!", operand=operand)

        if tok.kind == TokenKind.TILDE:
            self._advance()
            operand = self._parse_unary()
            return A.UnOp(line=tok.line, col=tok.col, op="~", operand=operand)

        if tok.kind == TokenKind.AMP:
            self._advance()
            operand = self._parse_unary()
            return A.UnOp(line=tok.line, col=tok.col, op="&", operand=operand)

        if tok.kind == TokenKind.STAR:
            self._advance()
            operand = self._parse_unary()
            return A.UnOp(line=tok.line, col=tok.col, op="*", operand=operand)

        if tok.kind == TokenKind.SIZEOF:
            self._advance()
            self._expect(TokenKind.LPAREN)
            t = self._parse_type()
            self._expect(TokenKind.RPAREN)
            return A.Sizeof(line=tok.line, col=tok.col, type=t)

        return self._parse_postfix()

    def _parse_postfix(self) -> A.Node:
        expr = self._parse_primary()

        while True:
            tok = self._peek()

            if tok.kind == TokenKind.LPAREN:
                self._advance()
                args: list[A.Node] = []
                if not self._check(TokenKind.RPAREN):
                    while True:
                        args.append(self._parse_expr())
                        if not self._match(TokenKind.COMMA):
                            break
                self._expect(TokenKind.RPAREN)
                expr = A.Call(line=expr.line, col=expr.col,
                              callee=expr, args=args)
                continue

            if tok.kind == TokenKind.DOT:
                self._advance()
                field_tok = self._expect(TokenKind.IDENT, "field name")
                expr = A.MemberAccess(line=expr.line, col=expr.col,
                                      obj=expr, field=field_tok.value)
                continue

            if tok.kind == TokenKind.LBRACKET:
                self._advance()
                idx = self._parse_expr()
                self._expect(TokenKind.RBRACKET)
                expr = A.Index(line=expr.line, col=expr.col,
                               obj=expr, index=idx)
                continue
                
            if tok.kind == TokenKind.AS:
                self._advance()
                t = self._parse_type()
                expr = A.Cast(line=expr.line, col=expr.col, expr=expr, type=t)
                continue

            break

        return expr

    def _parse_primary(self) -> A.Node:
        tok = self._peek()

        if tok.kind == TokenKind.INT_LIT:
            self._advance()
            return A.IntLit(line=tok.line, col=tok.col,
                            value=self._parse_int_literal(tok.value),
                            raw=tok.value)

        if tok.kind == TokenKind.FLOAT_LIT:
            self._advance()
            return A.FloatLit(line=tok.line, col=tok.col,
                              value=float(tok.value.replace("_", "")),
                              raw=tok.value)

        if tok.kind == TokenKind.STRING_LIT:
            self._advance()
            return A.StringLit(line=tok.line, col=tok.col, value=tok.value)

        if tok.kind == TokenKind.CHAR_LIT:
            self._advance()
            return A.CharLit(line=tok.line, col=tok.col, value=tok.value)

        if tok.kind == TokenKind.TRUE:
            self._advance()
            return A.BoolLit(line=tok.line, col=tok.col, value=True)
        if tok.kind == TokenKind.FALSE:
            self._advance()
            return A.BoolLit(line=tok.line, col=tok.col, value=False)
        if tok.kind == TokenKind.NULL:
            self._advance()
            return A.NullLit(line=tok.line, col=tok.col)

        if tok.kind == TokenKind.IDENT:
            self._advance()
            return A.Ident(line=tok.line, col=tok.col, name=tok.value)

        if tok.kind == TokenKind.LPAREN:
            self._advance()
            expr = self._parse_expr()
            self._expect(TokenKind.RPAREN)
            return expr

        raise LoomError(
            f"expected expression, got {tok.kind.name} {tok.value!r}",
            self.filename, tok.line, tok.col
        )

    @staticmethod
    def _parse_int_literal(raw: str) -> int:
        s = raw.replace("_", "")
        if s.startswith(("0x", "0X")):
            return int(s, 16)
        if s.startswith(("0b", "0B")):
            return int(s, 2)
        if s.startswith(("0o", "0O")):
            return int(s, 8)
        return int(s, 10)

def parse(source: str, filename: str = "<input>") -> A.Module:
   tokens = Lexer(source, filename).tokenize()
   return Parser(tokens, filename).parse_module()