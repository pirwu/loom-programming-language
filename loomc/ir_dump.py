from . import ir as I

def dump_module(mod: I.IRModule) -> str:
    out = [f"module {mod.name}"]
    if mod.strings:
        out.append("  strings:")
        for i, s in enumerate(mod.strings):
            out.append(f"    [{i}] {s!r}")

    for fn in mod.functions:
        if fn.is_extern:
            out.append(f"extern fn {fn.name}(...) -> size{fn.ret_size}")
            continue

        params = ", ".join(f"{p.name}:size{p.size}" for p in fn.params)
        out.append(f"fn {fn.name}({params}) -> size{fn.ret_size} {{")
        if fn.locals:
            out.append("  locals:")
            for l in fn.locals:
                out.append(f"    {l.name}: size{l.size}")
        for ins in fn.instrs:
            out.append("  " + _fmt_instr(ins))
        out.append("}")
    return "\n".join(out)

def _fmt_val(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, I.Const):
        if v.is_string:
            return f"str[{v.value}]"
        return str(v.value)
    if isinstance(v, I.Temp):
        return f"%t{v.id}"
    if isinstance(v, I.Var):
        return f"%{v.name}"
    if isinstance(v, I.Label):
        return f".{v.name}"
    return repr(v)


def _fmt_instr(i: I.Instr) -> str:
    if isinstance(i, I.LabelInstr):
        return f"{i.name}:"
    if isinstance(i, I.Mov):
        return f"{_fmt_val(i.dst)} = {_fmt_val(i.src)}"
    if isinstance(i, I.BinOp):
        return f"{_fmt_val(i.dst)} = {_fmt_val(i.a)} {i.op} {_fmt_val(i.b)}"
    if isinstance(i, I.Cmp):
        return f"{_fmt_val(i.dst)} = ({_fmt_val(i.a)} {i.op} {_fmt_val(i.b)})"
    if isinstance(i, I.UnOp):
        return f"{_fmt_val(i.dst)} = {i.op}{_fmt_val(i.a)}"
    if isinstance(i, I.Load):
        return f"{_fmt_val(i.dst)} = *[{i.size}]{_fmt_val(i.addr)}"
    if isinstance(i, I.Store):
        return f"*[{i.size}]{_fmt_val(i.addr)} = {_fmt_val(i.src)}"
    if isinstance(i, I.AddrOf):
        return f"{_fmt_val(i.dst)} = &{_fmt_val(i.var)}"
    if isinstance(i, I.LeaField):
        return f"{_fmt_val(i.dst)} = {_fmt_val(i.base)} + {i.offset}"
    if isinstance(i, I.LeaIndex):
        return f"{_fmt_val(i.dst)} = {_fmt_val(i.base)} + {_fmt_val(i.index)}*{i.elem_size}"
    if isinstance(i, I.Call):
        args = ", ".join(_fmt_val(a) for a in i.args)
        return f"{_fmt_val(i.dst)} = call {i.target}({args})"
    if isinstance(i, I.Syscall):
        args = ", ".join(_fmt_val(a) for a in i.args)
        return f"{_fmt_val(i.dst)} = syscall {_fmt_val(i.nr)}({args})"
    if isinstance(i, I.Ret):
        return f"ret {_fmt_val(i.value) if i.value else ''}".rstrip()
    if isinstance(i, I.Jmp):
        return f"jmp {i.target}"
    if isinstance(i, I.JmpIf):
        return f"if {_fmt_val(i.cond)} jmp {i.target}"
    if isinstance(i, I.JmpIfZero):
        return f"ifz {_fmt_val(i.cond)} jmp {i.target}"
    if isinstance(i, I.Alloc):
        return f"{_fmt_val(i.dst)} = alloc({_fmt_val(i.size)})"
    if isinstance(i, I.Free):
        return f"free({_fmt_val(i.ptr)})"
    return f"<{type(i).__name__}>"