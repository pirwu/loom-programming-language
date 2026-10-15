"""
AST -> IR LOOM v1.
"""

from __future__ import annotations

from . import ast as A
from . import ir as I
from .errors import LoomError

TYPE_SIZE: dict[str, int] = {
    "i8": 1, "i16": 2, "i32": 4, "i64": 8,
    "u8": 1, "u16": 2, "u32": 4, "u64": 8,
    "f32": 4, "f64": 8,
    "bool": 1, "void": 0,
}

CONSOLE_BUILTINS = {
    "print", "print_int", "print_uint", "print_hex",
    "print_bool", "print_char", "eprint", "eprint_int",
    "input", "input_line",
}

class LowerModule:
    def __init__(self, module_name: str, filename: str = "<input>"):
        self.module_name = module_name
        self.filename = filename
        self.module = I.IRModule(name=module_name)
        self._temp_counter = 0
        self._label_counter = 0
        self._current_fn: I.IRFunction | None = None
        self._locals: dict[str, A.TypeRef] = {}
        self._strings: dict[str, int] = {}
        self._struct_field_types: dict[str, dict[str, A.TypeRef]] = {}
        self._structs: dict[str, dict[str, int]] = {}
        self._struct_sizes: dict[str, int] = {}
        self._enums: dict[str, dict[str, int]] = {}
        self._consts: dict[str, int] = {}
        self._enum_values: dict[str, int] = {}
        self._enum_names: dict[str, dict[str, int]] = {}
        self._globals: dict[str, A.TypeRef] = {}
        self._imports: dict[str, str] = {}
        
    def _register_const(self, c: A.ConstDecl) -> None:
        if c.name in self._consts:
            raise LoomError(f"duplicate const {c.name!r}",
                            self.filename, c.line, c.col)
        value = self._eval_const_expr(c.value)
        self._consts[c.name] = value

    def _eval_const_expr(self, e: A.Node) -> int:
        if isinstance(e, A.IntLit):
            return e.value
        if isinstance(e, A.CharLit):
            return ord(e.value)
        if isinstance(e, A.BoolLit):
            return 1 if e.value else 0
        if isinstance(e, A.NullLit):
            return 0
        if isinstance(e, A.Ident):
            if e.name in self._consts:
                return self._consts[e.name]
            raise LoomError(
                f"const: unknown name {e.name!r}",
                self.filename, e.line, e.col
            )
        if isinstance(e, A.MemberAccess):
            if isinstance(e.obj, A.Ident):
                key = f"{e.obj.name}.{e.field}"
                if key in self._enum_values:
                    return self._enum_values[key]
            raise LoomError(
                f"const: unknown enum member {e.field!r}",
                self.filename, e.line, e.col
            )
        if isinstance(e, A.UnOp):
            inner = self._eval_const_expr(e.operand)
            if e.op == "-":  return -inner
            if e.op == "~":  return ~inner
            if e.op == "!":  return 0 if inner else 1
            raise LoomError(f"const: unsupported unary {e.op!r}",
                            self.filename, e.line, e.col)
        if isinstance(e, A.BinOp):
            a = self._eval_const_expr(e.left)
            b = self._eval_const_expr(e.right)
            op = e.op
            if op == "+":  return a + b
            if op == "-":  return a - b
            if op == "*":  return a * b
            if op == "/":
                if b == 0:
                    raise LoomError("const: division by zero",
                                    self.filename, e.line, e.col)
                return int(a / b) if a * b >= 0 else -(-a // b) if False else a // b
            if op == "%":
                if b == 0:
                    raise LoomError("const: modulo by zero",
                                    self.filename, e.line, e.col)
                return a % b
            if op == "&":  return a & b
            if op == "|":  return a | b
            if op == "^":  return a ^ b
            if op == "<<": return a << b
            if op == ">>": return a >> b
            if op == "==": return 1 if a == b else 0
            if op == "!=": return 1 if a != b else 0
            if op == "<":  return 1 if a < b else 0
            if op == "<=": return 1 if a <= b else 0
            if op == ">":  return 1 if a > b else 0
            if op == ">=": return 1 if a >= b else 0
            raise LoomError(f"const: unsupported binop {op!r}",
                            self.filename, e.line, e.col)
        if isinstance(e, A.Sizeof):
            return self._type_size(e.type)
        raise LoomError(
            f"const: unsupported expression {type(e).__name__}",
            self.filename, e.line, e.col
        )
        
    def _register_enum(self, e: A.EnumDecl) -> None:
        if e.name in self._enum_names:
            raise LoomError(f"duplicate enum {e.name!r}",
                            self.filename, e.line, e.col)
        variants: dict[str, int] = {}
        for v in e.variants:
            variants[v.name] = v.value if v.value is not None else 0
            self._enum_values[f"{e.name}.{v.name}"] = variants[v.name]
        self._enum_names[e.name] = variants
        
    def _register_struct(self, s: A.StructDecl) -> None:
        if s.name in self._structs:
            raise LoomError(f"duplicate struct {s.name!r}",
                            self.filename, s.line, s.col)
        offsets: dict[str, int] = {}
        field_types: dict[str, A.TypeRef] = {}
        cur = 0
        max_align = 1
        for f in s.fields:
            fsize = self._type_size(f.type)
            falign = self._align_of(f.type)
            if falign > max_align:
                max_align = falign
            cur = (cur + falign - 1) // falign * falign
            offsets[f.name] = cur
            field_types[f.name] = f.type
            cur += fsize
        cur = (cur + max_align - 1) // max_align * max_align
        self._structs[s.name] = offsets
        self._struct_field_types[s.name] = field_types
        self._struct_sizes[s.name] = cur

    def _align_of(self, t: A.TypeRef) -> int:
        if t.name == "ptr":
            return 8
        if t.name == "array":
            return self._align_of(t.inner)
        size = self._type_size(t)
        if size >= 8: return 8
        if size >= 4: return 4
        if size >= 2: return 2
        return 1
        
    def lower(self, mod: A.Module, imports: list[str] = None) -> I.IRModule:
        for imp in (imports or mod.imports):
            self._imports[imp] = imp

        for d in mod.decls:
            if isinstance(d, A.StructDecl):
                self._register_struct(d)

        for d in mod.decls:
            if isinstance(d, A.EnumDecl):
                self._register_enum(d)

        for d in mod.decls:
            if isinstance(d, A.ConstDecl):
                self._register_const(d)
                
        for d in mod.decls:
            if isinstance(d, A.GlobalVarDecl):
                self._globals[d.name] = d.type
                size = self._type_size(d.type)
                init = None
                if d.value is not None:
                    init = self._eval_const_expr(d.value)
                self.module.globals.append(
                    I.IRGlobal(name=d.name, size=size, init=init)
                )

        for d in mod.decls:
            if isinstance(d, A.FnDecl):
                if d.is_extern:
                    sym_name = d.name
                elif self.module_name == "main" and d.name == "main":
                    sym_name = "main"
                else:
                    sym_name = f"{self.module_name}_{d.name}"
                fn = I.IRFunction(
                    name=sym_name,
                    is_export=d.is_export,
                    is_extern=d.is_extern,
                )
                for p in d.params:
                    fn.params.append(I.IRParam(name=p.name,
                                               size=self._type_size(p.type)))
                fn.ret_size = self._type_size(d.ret_type) if d.ret_type else 0
                self.module.functions.append(fn)

        for d in mod.decls:
            if isinstance(d, A.FnDecl) and not d.is_extern:
                self._lower_fn(d)

        return self.module

    def _new_temp(self) -> I.Temp:
        t = I.Temp(self._temp_counter)
        self._temp_counter += 1
        return t

    def _new_label(self, hint: str = "L") -> str:
        name = f"{hint}{self._label_counter}"
        self._label_counter += 1
        return name

    def _type_size(self, t: A.TypeRef | None) -> int:
        if t is None:
            return 0
        if t.name == "ptr":
            return 8
        if t.name == "array":
            inner = self._type_size(t.inner)
            return inner * (t.array_len or 0)
        if t.name in TYPE_SIZE:
            return TYPE_SIZE[t.name]
        if t.name in self._struct_sizes:
            return self._struct_sizes[t.name]
        if t.name in self._enums:
            return 4
        raise LoomError(f"lower: unknown type {t.name!r}",
                        self.filename, t.line, t.col)

    def _emit(self, instr: I.Instr) -> None:
        assert self._current_fn is not None
        self._current_fn.instrs.append(instr)

    def _intern_string(self, s: str) -> int:
        if s in self._strings:
            return self._strings[s]
        idx = len(self.module.strings)
        self.module.strings.append(s)
        self._strings[s] = idx
        return idx

    def _lower_fn(self, fn: A.FnDecl) -> None:
        if self.module_name == "main" and fn.name == "main":
            sym_name = "main"
        else:
            sym_name = f"{self.module_name}_{fn.name}"

        ir_fn = None
        for f in self.module.functions:
            if f.name == sym_name:
                ir_fn = f
                break
        assert ir_fn is not None

        self._current_fn = ir_fn
        self._locals = {}
        for p in fn.params:
            self._locals[p.name] = p.type

        if fn.body:
            self._lower_block(fn.body)

        if ir_fn.ret_size != 0:
            if not ir_fn.instrs or not isinstance(ir_fn.instrs[-1], I.Ret):
                self._emit(I.Ret(line=fn.line, col=fn.col, value=I.Const(0)))
        else:
            if not ir_fn.instrs or not isinstance(ir_fn.instrs[-1], I.Ret):
                self._emit(I.Ret(line=fn.line, col=fn.col, value=None))

        param_names = [p.name for p in ir_fn.params]
        for name, ty in self._locals.items():
            if name not in param_names:
                ir_fn.locals.append(I.IRParam(name=name, size=self._type_size(ty)))

        self._current_fn = None

    def _lower_block(self, blk: A.Block) -> None:
        for stmt in blk.stmts:
            self._lower_stmt(stmt)

    def _lower_stmt(self, s: A.Node) -> None:
        if isinstance(s, A.VarDecl):
            self._locals[s.name] = s.type
            if s.value is not None:
                v = self._lower_expr(s.value)
                self._emit(I.Mov(line=s.line, col=s.col,
                                 dst=I.Var(s.name), src=v))
            return

        if isinstance(s, A.Assign):
            self._lower_assign(s)
            return

        if isinstance(s, A.Ret):
            if s.value is None:
                self._emit(I.Ret(line=s.line, col=s.col, value=None))
            else:
                v = self._lower_expr(s.value)
                self._emit(I.Ret(line=s.line, col=s.col, value=v))
            return

        if isinstance(s, A.ExprStmt):
            self._lower_expr(s.expr)
            return

        if isinstance(s, A.If):
            self._lower_if(s)
            return

        if isinstance(s, A.While):
            self._lower_while(s)
            return

        if isinstance(s, A.Loop):
            self._lower_loop(s)
            return

        if isinstance(s, A.Break):
            if not getattr(self, "_loop_end_labels", None):
                raise LoomError("break outside loop",
                                self.filename, s.line, s.col)
            self._emit(I.Jmp(line=s.line, col=s.col,
                             target=self._loop_end_labels[-1]))
            return

        if isinstance(s, A.Continue):
            if not getattr(self, "_loop_start_labels", None):
                raise LoomError("continue outside loop",
                                self.filename, s.line, s.col)
            self._emit(I.Jmp(line=s.line, col=s.col,
                             target=self._loop_start_labels[-1]))
            return

        if isinstance(s, A.Label):
            self._emit(I.LabelInstr(line=s.line, col=s.col, name=s.name))
            return

        if isinstance(s, A.Jmp):
            self._emit(I.Jmp(line=s.line, col=s.col, target=s.label))
            return

        raise LoomError(
            f"lower: unsupported statement {type(s).__name__}",
            self.filename, s.line, s.col
        )

    def _lower_assign(self, s: A.Assign) -> None:
        if s.op == "=":
            value = self._lower_expr(s.value)
            self._store_to_lvalue(s.target, value, s.line, s.col)
            return

        base_op = s.op[:-1]
        old = self._lower_expr(s.target)
        right = self._lower_expr(s.value)
        tmp = self._new_temp()
        self._emit(I.BinOp(line=s.line, col=s.col, op=base_op,
                           dst=tmp, a=old, b=right))
        self._store_to_lvalue(s.target, tmp, s.line, s.col)

    def _store_to_lvalue(self, target: A.Node, value: I.Value,
                         line: int, col: int) -> None:
        if isinstance(target, A.Ident) and target.name in self._consts:
            raise LoomError(
                f"lower: cannot assign to const {target.name!r}",
                self.filename, line, col
            )
            
        if isinstance(target, A.Ident):
            if target.name in self._locals:
                dst = I.Var(target.name)
            elif target.name in self._globals:
                dst = I.Global(target.name)
            else:
                raise LoomError(
                    f"lower: assignment to unknown variable "
                    f"{target.name!r}",
                    self.filename, line, col
                )
            self._emit(I.Mov(line=line, col=col, dst=dst, src=value))
            return

        if isinstance(target, A.UnOp) and target.op == "*":
            addr = self._lower_expr(target.operand)
            self._emit(I.Store(line=line, col=col,
                               addr=addr, src=value, size=8))
            return

        if isinstance(target, A.Index):
            base, elem_size = self._resolve_index_base(
                target.obj, line, col)
            idx = self._lower_expr(target.index)
            addr = self._new_temp()
            self._emit(I.LeaIndex(line=line, col=col,
                                  dst=addr, base=base,
                                  index=idx, elem_size=elem_size))
            self._emit(I.Store(line=line, col=col,
                               addr=addr, src=value, size=elem_size))
            return

        if isinstance(target, A.MemberAccess):
            self._lower_member_write(target, value, line, col)
            return

        raise LoomError(
            f"lower: unsupported assignment target "
            f"({type(target).__name__})",
            self.filename, line, col
        )

    def _lower_if(self, s: A.If) -> None:
        else_lbl = self._new_label("else")
        end_lbl = self._new_label("endif")

        cond = self._lower_expr(s.cond)
        self._emit(I.JmpIfZero(line=s.line, col=s.col,
                               cond=cond, target=else_lbl))

        self._lower_block(s.then_block)

        if s.else_block is not None:
            self._emit(I.Jmp(line=s.line, col=s.col, target=end_lbl))
            self._emit(I.LabelInstr(name=else_lbl))
            self._lower_block(s.else_block)
            self._emit(I.LabelInstr(name=end_lbl))
        else:
            self._emit(I.LabelInstr(name=else_lbl))

    def _lower_while(self, s: A.While) -> None:
        start_lbl = self._new_label("while_start")
        end_lbl = self._new_label("while_end")

        if not hasattr(self, "_loop_start_labels"):
            self._loop_start_labels: list[str] = []
            self._loop_end_labels: list[str] = []

        self._loop_start_labels.append(start_lbl)
        self._loop_end_labels.append(end_lbl)

        self._emit(I.LabelInstr(name=start_lbl))
        cond = self._lower_expr(s.cond)
        self._emit(I.JmpIfZero(line=s.line, col=s.col,
                               cond=cond, target=end_lbl))
        self._lower_block(s.body)
        self._emit(I.Jmp(line=s.line, col=s.col, target=start_lbl))
        self._emit(I.LabelInstr(name=end_lbl))

        self._loop_start_labels.pop()
        self._loop_end_labels.pop()

    def _lower_loop(self, s: A.Loop) -> None:
        start_lbl = self._new_label("loop_start")
        end_lbl = self._new_label("loop_end")

        if not hasattr(self, "_loop_start_labels"):
            self._loop_start_labels: list[str] = []
            self._loop_end_labels: list[str] = []

        self._loop_start_labels.append(start_lbl)
        self._loop_end_labels.append(end_lbl)

        self._emit(I.LabelInstr(name=start_lbl))
        self._lower_block(s.body)
        self._emit(I.Jmp(line=s.line, col=s.col, target=start_lbl))
        self._emit(I.LabelInstr(name=end_lbl))

        self._loop_start_labels.pop()
        self._loop_end_labels.pop()

    def _lower_expr(self, e: A.Node) -> I.Value:
        if isinstance(e, A.IntLit):
            return I.Const(e.value)

        if isinstance(e, A.BoolLit):
            return I.Const(1 if e.value else 0)

        if isinstance(e, A.NullLit):
            return I.Const(0)

        if isinstance(e, A.CharLit):
            return I.Const(ord(e.value))

        if isinstance(e, A.StringLit):
            idx = self._intern_string(e.value)
            return I.Const(idx, is_string=True)

        if isinstance(e, A.FloatLit):
            raise LoomError("lower: float literals not yet supported",
                            self.filename, e.line, e.col)

        if isinstance(e, A.Ident):
            if e.name in self._consts:
                return I.Const(self._consts[e.name])
            if e.name in self._enum_names:
                raise LoomError(
                    f"lower: enum {e.name!r} used as value; "
                    f"use {e.name}.Variant",
                    self.filename, e.line, e.col
                )
            if e.name in self._locals:
                return I.Var(e.name)
            if e.name in self._globals:
                return I.Global(e.name)
            raise LoomError(
                f"lower: unknown variable {e.name!r}",
                self.filename, e.line, e.col
            )

        if isinstance(e, A.BinOp):
            return self._lower_binop(e)

        if isinstance(e, A.UnOp):
            return self._lower_unop(e)

        if isinstance(e, A.Call):
            return self._lower_call(e)

        if isinstance(e, A.MemberAccess):
            if isinstance(e.obj, A.Ident) and e.obj.name in self._enum_names:
                key = f"{e.obj.name}.{e.field}"
                if key not in self._enum_values:
                    raise LoomError(
                        f"lower: enum {e.obj.name!r} has no variant "
                        f"{e.field!r}",
                        self.filename, e.line, e.col
                    )
                return I.Const(self._enum_values[key])
            return self._lower_member_read(e)

        if isinstance(e, A.Index):
            return self._lower_index_read(e)

        if isinstance(e, A.Cast):
            return self._lower_expr(e.expr)

        if isinstance(e, A.Sizeof):
            return I.Const(self._type_size(e.type))

        raise LoomError(
            f"lower: unsupported expression {type(e).__name__}",
            self.filename, e.line, e.col
        )
        
    def _lower_index_read(self, e: A.Index) -> I.Value:
        base, elem_size = self._resolve_index_base(e.obj, e.line, e.col)
        idx = self._lower_expr(e.index)
        addr = self._new_temp()
        self._emit(I.LeaIndex(line=e.line, col=e.col,
                              dst=addr, base=base,
                              index=idx, elem_size=elem_size))
        result = self._new_temp()
        self._emit(I.Load(line=e.line, col=e.col,
                          dst=result, addr=addr, size=elem_size))
        return result

    def _resolve_index_base(self, obj: A.Node, line: int, col: int) -> tuple[I.Value, int]:
        if not isinstance(obj, A.Ident):
            raise LoomError(
                "lower: index base must be identifier in v0.x",
                self.filename, line, col
            )
        name = obj.name
        if name not in self._locals:
            raise LoomError(
                f"lower: unknown variable {name!r}",
                self.filename, line, col
            )
        ty = self._locals[name]

        if ty.name == "ptr":
            elem_size = self._type_size(ty.inner)
            return I.Var(name), elem_size

        if ty.name == "array":
            elem_size = self._type_size(ty.inner)
            addr = self._new_temp()
            self._emit(I.AddrOf(line=line, col=col,
                                dst=addr, var=I.Var(name)))
            return addr, elem_size

        raise LoomError(
            f"lower: cannot index {name!r} (type: {ty.name})",
            self.filename, line, col
        )

    def _lower_binop(self, e: A.BinOp) -> I.Value:
        if e.op == "&&":
            return self._lower_logical_and(e)
        if e.op == "||":
            return self._lower_logical_or(e)

        a = self._lower_expr(e.left)
        b = self._lower_expr(e.right)
        t = self._new_temp()

        if e.op in ("+", "-", "*", "/", "%", "&", "|", "^", "<<", ">>"):
            self._emit(I.BinOp(line=e.line, col=e.col, op=e.op,
                               dst=t, a=a, b=b))
            return t

        if e.op in ("==", "!=", "<", "<=", ">", ">="):
            self._emit(I.Cmp(line=e.line, col=e.col, op=e.op,
                             dst=t, a=a, b=b))
            return t

        raise LoomError(f"lower: unknown binary op {e.op!r}",
                        self.filename, e.line, e.col)

    def _lower_logical_and(self, e: A.BinOp) -> I.Value:
        end_lbl = self._new_label("and_end")
        t = self._new_temp()
        self._emit(I.Mov(line=e.line, col=e.col, dst=t, src=I.Const(0)))
        a = self._lower_expr(e.left)
        self._emit(I.JmpIfZero(line=e.line, col=e.col, cond=a, target=end_lbl))
        b = self._lower_expr(e.right)
        self._emit(I.Cmp(line=e.line, col=e.col, op="!=",
                         dst=t, a=b, b=I.Const(0)))
        self._emit(I.LabelInstr(name=end_lbl))
        return t

    def _lower_logical_or(self, e: A.BinOp) -> I.Value:
        end_lbl = self._new_label("or_end")
        t = self._new_temp()
        self._emit(I.Mov(line=e.line, col=e.col, dst=t, src=I.Const(1)))
        a = self._lower_expr(e.left)
        self._emit(I.JmpIf(line=e.line, col=e.col, cond=a, target=end_lbl))
        b = self._lower_expr(e.right)
        self._emit(I.Cmp(line=e.line, col=e.col, op="!=",
                         dst=t, a=b, b=I.Const(0)))
        self._emit(I.LabelInstr(name=end_lbl))
        return t

    def _lower_unop(self, e: A.UnOp) -> I.Value:
        if e.op in ("-", "~"):
            a = self._lower_expr(e.operand)
            t = self._new_temp()
            self._emit(I.UnOp(line=e.line, col=e.col, op=e.op,
                              dst=t, a=a))
            return t

        if e.op == "!":
            a = self._lower_expr(e.operand)
            t = self._new_temp()
            self._emit(I.Cmp(line=e.line, col=e.col, op="==",
                             dst=t, a=a, b=I.Const(0)))
            return t
        
        if e.op == "&":
            if isinstance(e.operand, A.Cast):
                return self._lower_unop(
                    A.UnOp(line=e.line, col=e.col, op="&",
                           operand=e.operand.expr)
                )

            if isinstance(e.operand, A.Ident):
                t = self._new_temp()
                self._emit(I.AddrOf(line=e.line, col=e.col,
                                    dst=t, var=I.Var(e.operand.name)))
                return t

            if isinstance(e.operand, A.MemberAccess):
                base, offset, _ = self._resolve_member(
                    e.operand.obj, e.operand.field, e.line, e.col)
                t = self._new_temp()
                self._emit(I.LeaField(line=e.line, col=e.col,
                                      dst=t, base=base, offset=offset))
                return t

            if isinstance(e.operand, A.Index):
                base, elem_size = self._resolve_index_base(
                    e.operand.obj, e.line, e.col)
                idx = self._lower_expr(e.operand.index)
                t = self._new_temp()
                self._emit(I.LeaIndex(line=e.line, col=e.col,
                                      dst=t, base=base,
                                      index=idx, elem_size=elem_size))
                return t

            raise LoomError(
                f"lower: unsupported '&' operand ({type(e.operand).__name__})",
                self.filename, e.line, e.col
            )

        if e.op == "*":
            addr = self._lower_expr(e.operand)
            t = self._new_temp()
            self._emit(I.Load(line=e.line, col=e.col,
                              dst=t, addr=addr, size=8))
            return t

        raise LoomError(f"lower: unknown unary op {e.op!r}",
                        self.filename, e.line, e.col)

        if e.op == "*":
            addr = self._lower_expr(e.operand)
            t = self._new_temp()
            self._emit(I.Load(line=e.line, col=e.col,
                              dst=t, addr=addr, size=8))
            return t

        raise LoomError(f"lower: unknown unary op {e.op!r}",
                        self.filename, e.line, e.col)
                        
    def _resolve_member(self, obj: A.Node, field: str,
                        line: int, col: int) -> tuple[I.Value, int, int]:

        if not isinstance(obj, A.Ident):
            raise LoomError(
                "lower: field access base must be identifier in v0.x",
                self.filename, line, col
            )
        name = obj.name
        if name not in self._locals:
            raise LoomError(
                f"lower: unknown variable {name!r}",
                self.filename, line, col
            )
        ty = self._locals[name]

        if ty.name == "ptr":
            inner = ty.inner
            if inner is None or inner.name not in self._structs:
                raise LoomError(
                    f"lower: cannot access field of ptr to non-struct "
                    f"({inner.name if inner else '?'})",
                    self.filename, line, col
                )
            struct_name = inner.name
            base = I.Var(name)
        elif ty.name in self._structs:
            struct_name = ty.name
            addr = self._new_temp()
            self._emit(I.AddrOf(line=line, col=col,
                                dst=addr, var=I.Var(name)))
            base = addr
        else:
            raise LoomError(
                f"lower: {name!r} is not a struct "
                f"(type: {ty.name})",
                self.filename, line, col
            )

        offsets = self._structs[struct_name]
        if field not in offsets:
            raise LoomError(
                f"lower: struct {struct_name!r} has no field {field!r}",
                self.filename, line, col
            )
        offset = offsets[field]
        fsize = self._field_size(struct_name, field)
        return base, offset, fsize

    def _field_size(self, struct_name: str, field: str) -> int:
        ty = self._struct_field_types[struct_name][field]
        return self._type_size(ty)

    def _lower_member_read(self, e: A.MemberAccess) -> I.Value:
        base, offset, fsize = self._resolve_member(
            e.obj, e.field, e.line, e.col)
        addr = self._new_temp()
        self._emit(I.LeaField(line=e.line, col=e.col,
                              dst=addr, base=base, offset=offset))
        result = self._new_temp()
        self._emit(I.Load(line=e.line, col=e.col,
                          dst=result, addr=addr, size=fsize))
        return result

    def _lower_member_write(self, target: A.MemberAccess, value: I.Value,
                            line: int, col: int) -> None:
        base, offset, fsize = self._resolve_member(
            target.obj, target.field, line, col)
        addr = self._new_temp()
        self._emit(I.LeaField(line=line, col=col,
                              dst=addr, base=base, offset=offset))
        self._emit(I.Store(line=line, col=col,
                           addr=addr, src=value, size=fsize))

    def _lower_call(self, e: A.Call) -> I.Value:
        if isinstance(e.callee, A.Ident):
            name = e.callee.name

            if name == "alloc":
                if len(e.args) != 1:
                    raise LoomError("alloc expects 1 argument",
                                    self.filename, e.line, e.col)
                size = self._lower_expr(e.args[0])
                t = self._new_temp()
                self._emit(I.Alloc(line=e.line, col=e.col, dst=t, size=size))
                return t

            if name == "free":
                if len(e.args) != 1:
                    raise LoomError("free expects 1 argument",
                                    self.filename, e.line, e.col)
                ptr = self._lower_expr(e.args[0])
                self._emit(I.Free(line=e.line, col=e.col, ptr=ptr))
                return I.Const(0)

            if name == "realloc":
                if len(e.args) != 2:
                    raise LoomError("realloc expects 2 arguments",
                                    self.filename, e.line, e.col)
                ptr = self._lower_expr(e.args[0])
                size = self._lower_expr(e.args[1])
                t = self._new_temp()
                self._emit(I.Call(line=e.line, col=e.col, dst=t,
                                  target="realloc", args=[ptr, size]))
                return t

            is_extern = False
            for f in self.module.functions:
                if f.is_extern and f.name == name:
                    is_extern = True
                    break
                if f.is_extern and f.name == f"{self.module_name}_{name}":
                    is_extern = True
                    name = f.name
                    break

            if is_extern:
                target = name
            else:
                target = f"{self.module_name}_{name}"

        elif isinstance(e.callee, A.MemberAccess):
            if not isinstance(e.callee.obj, A.Ident):
                raise LoomError(
                    "lower: complex callee not supported",
                    self.filename, e.line, e.col
                )
            obj_name = e.callee.obj.name
            field = e.callee.field

            if obj_name in self._imports and self._imports[obj_name] == "console":
                target = f"console.{field}"
            elif obj_name in self._imports:
                mod_name = self._imports[obj_name]
                target = f"{mod_name}_{field}"
            else:
                raise LoomError(
                    f"lower: cannot call member of {obj_name!r}",
                    self.filename, e.line, e.col
                )
        else:
            raise LoomError(
                "lower: callee must be identifier or member access",
                self.filename, e.line, e.col
            )

        args = [self._lower_expr(a) for a in e.args]
        t = self._new_temp()
        self._emit(I.Call(line=e.line, col=e.col,
                          dst=t, target=target, args=args))
        return t
                
class Lower:
    def __init__(self, filenames: list[str] | None = None):
        self.filenames = filenames or []

    def lower_all(self, modules: list[tuple[str, A.Module]]) -> I.IRModule:
        combined = I.IRModule(name="__combined__")
        string_base = 0

        for filename, mod_ast in modules:
            lm = LowerModule(mod_ast.name, filename)
            ir_mod = lm.lower(mod_ast)

            for fn in ir_mod.functions:
                combined.functions.append(fn)
            for g in ir_mod.globals:
                combined.globals.append(g)

            for fn in ir_mod.functions:
                for ins in fn.instrs:
                    for v in _all_values(ins):
                        if isinstance(v, I.Const) and v.is_string:
                            v.value += string_base
            string_base += len(ir_mod.strings)
            combined.strings.extend(ir_mod.strings)

        return combined

def _all_values(ins: I.Instr):
    if isinstance(ins, I.Mov):
        yield ins.dst; yield ins.src
    elif isinstance(ins, I.BinOp):
        yield ins.dst; yield ins.a; yield ins.b
    elif isinstance(ins, I.Cmp):
        yield ins.dst; yield ins.a; yield ins.b
    elif isinstance(ins, I.UnOp):
        yield ins.dst; yield ins.a
    elif isinstance(ins, I.Load):
        yield ins.dst; yield ins.addr
    elif isinstance(ins, I.Store):
        yield ins.addr; yield ins.src
    elif isinstance(ins, I.AddrOf):
        yield ins.dst
    elif isinstance(ins, I.LeaField):
        yield ins.dst; yield ins.base
    elif isinstance(ins, I.LeaIndex):
        yield ins.dst; yield ins.base; yield ins.index
    elif isinstance(ins, I.Call):
        if ins.dst: yield ins.dst
        for a in ins.args: yield a
    elif isinstance(ins, I.Syscall):
        if ins.dst: yield ins.dst
        yield ins.nr
        for a in ins.args: yield a
    elif isinstance(ins, I.Ret):
        if ins.value: yield ins.value
    elif isinstance(ins, I.JmpIf):
        yield ins.cond
    elif isinstance(ins, I.JmpIfZero):
        yield ins.cond
    elif isinstance(ins, I.Alloc):
        yield ins.dst; yield ins.size
    elif isinstance(ins, I.Free):
        yield ins.ptr