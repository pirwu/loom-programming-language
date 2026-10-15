"""
Codegen IR -> byte x86-64
"""

from __future__ import annotations

import struct

from . import ir as I
from .errors import LoomError

RAX, RCX, RDX, RBX, RSP, RBP, RSI, RDI = 0, 1, 2, 3, 4, 5, 6, 7
R8, R9, R10, R11, R12, R13, R14, R15 = 8, 9, 10, 11, 12, 13, 14, 15

ARG_REGS = [RCX, RDX, R8, R9]

CC_E, CC_NE = 4, 5
CC_L, CC_LE, CC_G, CC_GE = 12, 14, 15, 13

CMP_CC: dict[str, int] = {
    "==": CC_E, "!=": CC_NE,
    "<": CC_L, "<=": CC_LE,
    ">": CC_G, ">=": CC_GE,
}

CONSOLE_BUILTINS = {
    "console.print", "console.print_int", "console.print_uint",
    "console.print_hex", "console.print_bool", "console.print_char",
    "console.eprint", "console.eprint_int",
    "console.input", "console.input_line",
}

SHADOW = 32

def _modrm(mod: int, reg: int, rm: int) -> int:
    return (mod << 6) | ((reg & 7) << 3) | (rm & 7)

def _rex(w: int = 0, r: int = 0, x: int = 0, b: int = 0) -> int:
    return 0x40 | ((w & 1) << 3) | ((r & 1) << 2) | ((x & 1) << 1) | (b & 1)

class FuncAsm:
    def __init__(self):
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.patches: list[tuple[int, str]] = []
        self.string_refs: list[tuple[int, int]] = []
        self.extern_calls: list[tuple[int, str]] = []
        self.local_calls: list[tuple[int, str]] = []

    def emit(self, *bs: int) -> int:
        off = len(self.code)
        for b in bs:
            self.code.append(b & 0xFF)
        return off

    def emit_bytes(self, data: bytes) -> int:
        off = len(self.code)
        self.code.extend(data)
        return off

    def define_label(self, name: str) -> None:
        self.labels[name] = len(self.code)

    def jmp_rel32(self) -> int:
        self.emit(0xE9)
        off = len(self.code)
        self.code.extend(b"\x00\x00\x00\x00")
        return off

    def jcc_rel32(self, cc: int) -> int:
        self.emit(0x0F, 0x80 + cc)
        off = len(self.code)
        self.code.extend(b"\x00\x00\x00\x00")
        return off

    def ref_string(self, idx: int, str_offset: int) -> None:
        self.emit(_rex(w=1, r=(RAX >> 3)), 0x8D, _modrm(0, RAX, 5))
        off = len(self.code)
        self.code.extend(struct.pack("<i", str_offset))
        self.string_refs.append((off, idx))

    def lea_rip_string(self, dst: int, idx: int, str_offset: int) -> None:
        self.emit(_rex(w=1, r=(dst >> 3)), 0x8D, _modrm(0, dst, 5))
        off = len(self.code)
        self.code.extend(struct.pack("<i", str_offset))
        self.string_refs.append((off, idx))

    def push_r(self, reg: int) -> None:
        if reg >= 8:
            self.emit(0x41)
        self.emit(0x50 + (reg & 7))

    def pop_r(self, reg: int) -> None:
        if reg >= 8:
            self.emit(0x41)
        self.emit(0x58 + (reg & 7))

    def mov_rr(self, dst: int, src: int) -> None:
        self.emit(_rex(w=1, r=(src >> 3), b=(dst >> 3)), 0x89, _modrm(3, src, dst))

    def mov_ri(self, dst: int, imm: int) -> None:
        self.emit(_rex(w=1, b=(dst >> 3)), 0xB8 + (dst & 7))
        self.emit_bytes(struct.pack("<Q", imm & 0xFFFFFFFFFFFFFFFF))

    def mov_ri32(self, dst: int, imm: int) -> None:
        if -0x80000000 <= imm <= 0x7FFFFFFF:
            self.emit(_rex(w=1, b=(dst >> 3)), 0xC7, _modrm(3, 0, dst))
            self.emit_bytes(struct.pack("<i", imm))
        else:
            self.mov_ri(dst, imm)

    def mov_mr(self, base: int, disp: int, src: int) -> None:
        self._emit_modrm_mem(0x89, src, base, disp, rex_w=1)

    def mov_rm(self, dst: int, base: int, disp: int) -> None:
        self._emit_modrm_mem(0x8B, dst, base, disp, rex_w=1)

    def mov_rm8(self, dst: int, base: int, disp: int) -> None:
        self._emit_modrm_mem(0x0F, dst, base, disp, rex_w=0, two_byte_opcode=0xB6)

    def mov_mr8(self, base: int, disp: int, src: int) -> None:
        self._emit_modrm_mem(0x88, src, base, disp, rex_w=0)

    def mov_rm16(self, dst: int, base: int, disp: int) -> None:
        self.emit(0x66)
        self._emit_modrm_mem(0x0F, dst, base, disp, rex_w=0, two_byte_opcode=0xB7)

    def mov_mr16(self, base: int, disp: int, src: int) -> None:
        self.emit(0x66)
        self._emit_modrm_mem(0x89, src, base, disp, rex_w=0)

    def mov_rm32(self, dst: int, base: int, disp: int) -> None:
        self._emit_modrm_mem(0x8B, dst, base, disp, rex_w=0)

    def mov_mr32(self, base: int, disp: int, src: int) -> None:
        self._emit_modrm_mem(0x89, src, base, disp, rex_w=0)

    def add_rr(self, dst: int, src: int) -> None:
        self.emit(_rex(w=1, r=(src >> 3), b=(dst >> 3)), 0x01, _modrm(3, src, dst))

    def sub_rr(self, dst: int, src: int) -> None:
        self.emit(_rex(w=1, r=(src >> 3), b=(dst >> 3)), 0x29, _modrm(3, src, dst))

    def imul_rr(self, dst: int, src: int) -> None:
        self.emit(_rex(w=1, r=(dst >> 3), b=(src >> 3)), 0x0F, 0xAF, _modrm(3, dst, src))

    def cqo(self) -> None:
        self.emit(0x48, 0x99)

    def idiv_r(self, reg: int) -> None:
        self.emit(_rex(w=1, b=(reg >> 3)), 0xF7, _modrm(3, 7, reg))

    def xor_rr(self, dst: int, src: int) -> None:
        self.emit(_rex(w=1, r=(src >> 3), b=(dst >> 3)), 0x31, _modrm(3, src, dst))

    def and_rr(self, dst: int, src: int) -> None:
        self.emit(_rex(w=1, r=(src >> 3), b=(dst >> 3)), 0x21, _modrm(3, src, dst))

    def or_rr(self, dst: int, src: int) -> None:
        self.emit(_rex(w=1, r=(src >> 3), b=(dst >> 3)), 0x09, _modrm(3, src, dst))

    def not_r(self, reg: int) -> None:
        self.emit(_rex(w=1, b=(reg >> 3)), 0xF7, _modrm(3, 2, reg))

    def neg_r(self, reg: int) -> None:
        self.emit(_rex(w=1, b=(reg >> 3)), 0xF7, _modrm(3, 3, reg))

    def shl_r_cl(self, reg: int) -> None:
        self.emit(_rex(w=1, b=(reg >> 3)), 0xD3, _modrm(3, 4, reg))

    def sar_r_cl(self, reg: int) -> None:
        self.emit(_rex(w=1, b=(reg >> 3)), 0xD3, _modrm(3, 7, reg))

    def cmp_rr(self, a: int, b: int) -> None:
        self.emit(_rex(w=1, r=(b >> 3), b=(a >> 3)), 0x39, _modrm(3, b, a))

    def test_rr(self, a: int, b: int) -> None:
        self.emit(_rex(w=1, r=(b >> 3), b=(a >> 3)), 0x85, _modrm(3, b, a))

    def setcc(self, cc: int, reg: int) -> None:
        rex = _rex(w=0, b=(reg >> 3))
        if rex != 0x40:
            self.emit(rex)
        self.emit(0x0F, 0x90 + cc, _modrm(3, 0, reg))

    def movzx_r8(self, dst: int, src: int) -> None:
        self.emit(_rex(w=1, r=(dst >> 3), b=(src >> 3)),
                  0x0F, 0xB6, _modrm(3, dst, src))

    def lea_rbp(self, dst: int, disp: int) -> None:
        rex = _rex(w=1, r=(dst >> 3), b=(RBP >> 3))
        if disp == 0:
            self.emit(rex, 0x8D, _modrm(1, dst, RBP), 0)
        elif -128 <= disp <= 127:
            self.emit(rex, 0x8D, _modrm(1, dst, RBP), disp & 0xFF)
        else:
            self.emit(rex, 0x8D, _modrm(2, dst, RBP))
            self.emit_bytes(struct.pack("<i", disp))

    def call_local(self, name: str) -> None:
        self.emit(0xE8)
        off = len(self.code)
        self.code.extend(b"\x00\x00\x00\x00")
        self.local_calls.append((off, name))

    def call_extern(self, name: str) -> None:
        self.emit(0xE8)
        off = len(self.code)
        self.code.extend(b"\x00\x00\x00\x00")
        self.extern_calls.append((off, name))

    def ret(self) -> None:
        self.emit(0xC3)

    def sub_ri(self, reg: int, imm: int) -> None:
        self.emit(_rex(w=1, b=(reg >> 3)), 0x81, _modrm(3, 5, reg))
        self.emit_bytes(struct.pack("<i", imm))

    def add_ri(self, reg: int, imm: int) -> None:
        self.emit(_rex(w=1, b=(reg >> 3)), 0x81, _modrm(3, 0, reg))
        self.emit_bytes(struct.pack("<i", imm))
        
    def _emit_modrm_mem(self, opcode: int, reg: int, base: int, disp: int,
                        rex_w: int, two_byte_opcode: int = 0) -> None:
        need_sib = (base & 7) == 4

        rex = _rex(w=rex_w, r=(reg >> 3), b=(base >> 3))
        if rex_w == 0 or rex != 0x40:
            self.emit(rex)

        if two_byte_opcode:
            self.emit(opcode, two_byte_opcode)
        else:
            self.emit(opcode)

        if disp == 0 and (base & 7) != 5 and not need_sib:
            self.emit(_modrm(0, reg, base))
        elif disp == 0 and need_sib:
            self.emit(_modrm(0, reg, 4))
            self.emit((4 << 3) | (base & 7))
        elif disp == 0 and (base & 7) == 5:
            self.emit(_modrm(1, reg, base), 0)
        elif -128 <= disp <= 127:
            if need_sib:
                self.emit(_modrm(1, reg, 4))
                self.emit((4 << 3) | (base & 7), disp & 0xFF)
            else:
                self.emit(_modrm(1, reg, base), disp & 0xFF)
        else:
            if need_sib:
                self.emit(_modrm(2, reg, 4))
                self.emit((4 << 3) | (base & 7))
            else:
                self.emit(_modrm(2, reg, base))
            self.emit_bytes(struct.pack("<i", disp))
            
    def lea_rip_global(self, dst: int, name: str) -> None:
        self.emit(_rex(w=1, r=(dst >> 3)), 0x8D, _modrm(0, dst, 5))
        off = len(self.code)
        self.code.extend(b"\x00\x00\x00\x00")
        self.extern_calls.append((off, name))

    def mov_rip_global(self, dst: int, name: str) -> None:
        self.emit(_rex(w=1, r=(dst >> 3)), 0x8B, _modrm(0, dst, 5))
        off = len(self.code)
        self.code.extend(b"\x00\x00\x00\x00")
        self.extern_calls.append((off, name))

    def mov_global_r(self, name: str, src: int) -> None:
        self.emit(_rex(w=1, r=(src >> 3)), 0x89, _modrm(0, src, 5))
        off = len(self.code)
        self.code.extend(b"\x00\x00\x00\x00")
        self.extern_calls.append((off, name))

class Codegen:
    def __init__(self, module: I.IRModule, filename: str = "<input>"):
        self.module = module
        self.filename = filename
        self.text = bytearray()
        self.rodata = bytearray()
        self.func_offsets: dict[str, int] = {}
        self.extern_symbols: set[str] = set()
        self.relocs: list[tuple[int, str, object]] = []
        self._asm: FuncAsm | None = None
        self._fn: I.IRFunction | None = None
        self._slot: dict[str, int] = {}
        self._frame_size = 0
        self._string_offsets: list[int] = []
        self.data = bytearray()
        self.data_symbols: dict[str, int] = {}
        self.data_relocs: list[tuple[int, str, int]] = []

    def generate(self) -> bytes:
        self._prepare_rodata()
        self._prepare_data()

        for fn in self.module.functions:
            if fn.is_extern:
                continue
            self._gen_function(fn)

        from .coff import build_object
        return build_object(
            text=bytes(self.text),
            rodata=bytes(self.rodata),
            data=bytes(self.data),
            functions=self.func_offsets,
            data_symbols=self.data_symbols,
            externs=sorted(self.extern_symbols),
            relocs=self.relocs,
        )

    def dump_asm(self) -> str:
        out = []
        for i in range(0, len(self.text), 16):
            chunk = self.text[i:i+16]
            hexs = " ".join(f"{b:02x}" for b in chunk)
            out.append(f"{i:08x}  {hexs}")
        return "\n".join(out)

    def _prepare_rodata(self) -> None:
        for s in self.module.strings:
            self._string_offsets.append(len(self.rodata))
            self.rodata.extend(s.encode("utf-8"))
            self.rodata.append(0)

    def _string_rodata_offset(self, idx: int) -> int:
        return self._string_offsets[idx]
        
    def _prepare_data(self) -> None:
        for g in self.module.globals:
            align = min(g.size if g.size > 0 else 8, 8)
            if align == 0:
                align = 1
            while len(self.data) % align != 0:
                self.data.append(0)
            self.data_symbols[g.name] = len(self.data)
            if g.init is None:
                self.data.extend(b"\x00" * g.size)
            else:
                v = g.init & 0xFFFFFFFFFFFFFFFF
                self.data.extend(struct.pack("<Q", v)[:g.size])
        
    def _gen_function(self, fn: I.IRFunction) -> None:
        self._fn = fn
        self._asm = FuncAsm()
        self._slot = {}

        self.func_offsets[fn.name] = len(self.text)

        self._asm.push_r(RBP)
        self._asm.mov_rr(RBP, RSP)
        self._asm.push_r(RBX)

        self._assign_slots(fn)
        frame = self._frame_size
        if frame % 16 != 0:
            frame += 16 - (frame % 16)
        self._frame_size = frame
        if frame > 0:
            self._asm.sub_ri(RSP, frame)

        for i, p in enumerate(fn.params):
            if i < 4:
                self._asm.mov_mr(RBP, self._slot["p:" + p.name], ARG_REGS[i])
            else:
                self._asm.mov_rm(RAX, RBP, 16 + 8 * (i - 4))
                self._asm.mov_mr(RBP, self._slot["p:" + p.name], RAX)

        for ins in fn.instrs:
            self._gen_instr(ins)

        for off, label in self._asm.patches:
            if label not in self._asm.labels:
                raise LoomError(
                    f"codegen: undefined label {label!r} in {fn.name}",
                    self.filename, 0, 0
                )
            rel = self._asm.labels[label] - (off + 4)
            struct.pack_into("<i", self._asm.code, off, rel)

        base = len(self.text)
        for off, s_idx in self._asm.string_refs:
            str_off = self._string_offsets[s_idx]
            self.relocs.append((base + off, "rodata", str_off))
        for off, sym in self._asm.extern_calls:
            self.extern_symbols.add(sym)
            self.relocs.append((base + off, "extern", sym))
        for off, name in self._asm.local_calls:
            self.relocs.append((base + off, "local", name))

        self.text.extend(self._asm.code)

    def _assign_slots(self, fn: I.IRFunction) -> None:
        off = 8

        def alloc(size: int) -> int:
            nonlocal off
            off += 8
            return -off

        for p in fn.params:
            self._slot["p:" + p.name] = alloc(8)
        for l in fn.locals:
            self._slot["v:" + l.name] = alloc(8)

        temps: set[int] = set()
        for ins in fn.instrs:
            for v in self._instr_values(ins):
                if isinstance(v, I.Temp):
                    temps.add(v.id)
        for t in sorted(temps):
            self._slot["t:" + str(t)] = alloc(8)

        self._frame_size = off

    @staticmethod
    def _instr_values(ins: I.Instr):
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

    def _load_value(self, v: I.Value, reg: int) -> None:
        if isinstance(v, I.Const):
            if v.is_string:
                str_off = self._string_offsets[v.value]
                self._asm.lea_rip_string(reg, v.value, str_off)
            else:
                self._asm.mov_ri32(reg, v.value)
            return
            
        if isinstance(v, I.Global):
            self._asm.mov_rip_global(reg, v.name)
            self.extern_symbols.add(v.name)
            return
            
        if isinstance(v, I.Var):
            key = "p:" + v.name
            if key not in self._slot:
                key = "v:" + v.name
            if key not in self._slot:
                raise LoomError(f"codegen: undefined var {v.name!r}",
                                self.filename, 0, 0)
            self._asm.mov_rm(reg, RBP, self._slot[key])
            return
        if isinstance(v, I.Temp):
            key = "t:" + str(v.id)
            if key not in self._slot:
                raise LoomError(f"codegen: undefined temp %t{v.id}",
                                self.filename, 0, 0)
            self._asm.mov_rm(reg, RBP, self._slot[key])
            return
        raise LoomError(f"codegen: bad value {v!r}", self.filename, 0, 0)

    def _store_value(self, v: I.Value, reg: int) -> None:
        if isinstance(v, I.Global):
            self._asm.mov_global_r(v.name, reg)
            self.extern_symbols.add(v.name)
            return
        if isinstance(v, I.Var):
            key = "p:" + v.name
            if key not in self._slot:
                key = "v:" + v.name
            if key not in self._slot:
                raise LoomError(f"codegen: undefined var {v.name!r}",
                                self.filename, 0, 0)
            self._asm.mov_mr(RBP, self._slot[key], reg)
            return
        if isinstance(v, I.Temp):
            key = "t:" + str(v.id)
            if key not in self._slot:
                raise LoomError(f"codegen: undefined temp %t{v.id}",
                                self.filename, 0, 0)
            self._asm.mov_mr(RBP, self._slot[key], reg)
            return
        raise LoomError(f"codegen: cannot store to {v!r}",
                        self.filename, 0, 0)

    def _gen_instr(self, ins: I.Instr) -> None:
        if isinstance(ins, I.LabelInstr):
            self._asm.define_label(ins.name)
            return
        if isinstance(ins, I.Mov):
            self._load_value(ins.src, RAX)
            self._store_value(ins.dst, RAX)
            return
        if isinstance(ins, I.BinOp):
            self._gen_binop(ins); return
        if isinstance(ins, I.Cmp):
            self._gen_cmp(ins); return
        if isinstance(ins, I.UnOp):
            self._gen_unop(ins); return
        if isinstance(ins, I.Ret):
            self._gen_ret(ins); return
        if isinstance(ins, I.Jmp):
            off = self._asm.jmp_rel32()
            self._asm.patches.append((off, ins.target))
            return
        if isinstance(ins, I.JmpIf):
            self._load_value(ins.cond, RAX)
            self._asm.test_rr(RAX, RAX)
            off = self._asm.jcc_rel32(CC_NE)
            self._asm.patches.append((off, ins.target))
            return
        if isinstance(ins, I.JmpIfZero):
            self._load_value(ins.cond, RAX)
            self._asm.test_rr(RAX, RAX)
            off = self._asm.jcc_rel32(CC_E)
            self._asm.patches.append((off, ins.target))
            return
        if isinstance(ins, I.Call):
            self._gen_call(ins); return
        if isinstance(ins, I.AddrOf):
            self._gen_addrof(ins)
            return
        if isinstance(ins, I.Load):
            self._gen_load(ins)
            return
        if isinstance(ins, I.Store):
            self._gen_store(ins)
            return
        if isinstance(ins, I.Alloc):
            self._gen_alloc(ins)
            return
        if isinstance(ins, I.Free):
            self._gen_free(ins)
            return
        if isinstance(ins, I.LeaField):
            self._load_value(ins.base, RAX)
            if ins.offset != 0:
                self._asm.add_ri(RAX, ins.offset)
            self._store_value(ins.dst, RAX)
            return
        if isinstance(ins, I.LeaIndex):
            self._load_value(ins.base, RAX)
            self._load_value(ins.index, RCX)
            if ins.elem_size != 1:
                self._asm.mov_ri32(RDX, ins.elem_size)
                self._asm.imul_rr(RCX, RDX)
            self._asm.add_rr(RAX, RCX)
            self._store_value(ins.dst, RAX)
            return
        raise LoomError(
            f"codegen: unsupported IR {type(ins).__name__}",
            self.filename, ins.line, ins.col
        )

    def _gen_binop(self, ins: I.BinOp) -> None:
        self._load_value(ins.a, RAX)
        self._load_value(ins.b, RCX)
        op = ins.op
        if op == "+":    self._asm.add_rr(RAX, RCX)
        elif op == "-":  self._asm.sub_rr(RAX, RCX)
        elif op == "*":  self._asm.imul_rr(RAX, RCX)
        elif op == "/":  self._asm.cqo(); self._asm.idiv_r(RCX)
        elif op == "%":  self._asm.cqo(); self._asm.idiv_r(RCX); self._asm.mov_rr(RAX, RDX)
        elif op == "&":  self._asm.and_rr(RAX, RCX)
        elif op == "|":  self._asm.or_rr(RAX, RCX)
        elif op == "^":  self._asm.xor_rr(RAX, RCX)
        elif op == "<<": self._asm.shl_r_cl(RAX)
        elif op == ">>": self._asm.sar_r_cl(RAX)
        else:
            raise LoomError(f"codegen: unknown binop {op!r}",
                            self.filename, ins.line, ins.col)
        self._store_value(ins.dst, RAX)

    def _gen_cmp(self, ins: I.Cmp) -> None:
        self._load_value(ins.a, RAX)
        self._load_value(ins.b, RCX)
        self._asm.cmp_rr(RAX, RCX)
        cc = CMP_CC.get(ins.op)
        if cc is None:
            raise LoomError(f"codegen: unknown cmp {ins.op!r}",
                            self.filename, ins.line, ins.col)
        self._asm.setcc(cc, RAX)
        self._asm.movzx_r8(RAX, RAX)
        self._store_value(ins.dst, RAX)

    def _gen_unop(self, ins: I.UnOp) -> None:
        self._load_value(ins.a, RAX)
        if ins.op == "-":   self._asm.neg_r(RAX)
        elif ins.op == "~": self._asm.not_r(RAX)
        else:
            raise LoomError(f"codegen: unknown unop {ins.op!r}",
                            self.filename, ins.line, ins.col)
        self._store_value(ins.dst, RAX)
        
    def _gen_addrof(self, ins: I.AddrOf) -> None:
        if ins.var is None:
            raise LoomError("codegen: AddrOf without var",
                            self.filename, ins.line, ins.col)
        name = ins.var.name
        key = "p:" + name
        if key not in self._slot:
            key = "v:" + name
        if key not in self._slot:
            raise LoomError(
                f"codegen: address of unknown variable {name!r}",
                self.filename, ins.line, ins.col
            )
        self._asm.lea_rbp(RAX, self._slot[key])
        self._store_value(ins.dst, RAX)

    def _gen_load(self, ins: I.Load) -> None:
        self._load_value(ins.addr, RAX)
        size = ins.size
        if size == 1:
            self._asm.mov_rm8(RAX, RAX, 0)
        elif size == 2:
            self._asm.mov_rm16(RAX, RAX, 0)
        elif size == 4:
            self._asm.mov_rm32(RAX, RAX, 0)
        else:
            self._asm.mov_rm(RAX, RAX, 0)
        self._store_value(ins.dst, RAX)

    def _gen_store(self, ins: I.Store) -> None:
        self._load_value(ins.addr, RAX)
        self._load_value(ins.src, RCX)
        size = ins.size
        if size == 1:
            self._asm.mov_mr8(RAX, 0, RCX)
        elif size == 2:
            self._asm.mov_mr16(RAX, 0, RCX)
        elif size == 4:
            self._asm.mov_mr32(RAX, 0, RCX)
        else:
            self._asm.mov_mr(RAX, 0, RCX)

    def _gen_ret(self, ins: I.Ret) -> None:
        if ins.value is not None:
            self._load_value(ins.value, RAX)
        self._asm.mov_rm(RBX, RBP, -8)
        self._asm.mov_rr(RSP, RBP)
        self._asm.pop_r(RBP)
        self._asm.ret()

    def _gen_call(self, ins: I.Call) -> None:
        if ins.target in CONSOLE_BUILTINS:
            self._gen_console_builtin(ins)
            return

        n = len(ins.args)
        stack_args = max(0, n - 4)
        pad = 8 if (stack_args % 2 == 1) else 0

        total = SHADOW + 8 * stack_args + pad
        if total > 0:
            self._asm.sub_ri(RSP, total)

        for i in range(n - 1, 3, -1):
            self._load_value(ins.args[i], RAX)
            slot = SHADOW + 8 * (i - 4)
            self._asm.mov_mr(RSP, slot, RAX)

        for i in range(min(n, 4)):
            self._load_value(ins.args[i], ARG_REGS[i])

        if ins.target in self.func_offsets:
            self._asm.call_local(ins.target)
        else:
            self._asm.call_extern(ins.target)
            self.extern_symbols.add(ins.target)

        if total > 0:
            self._asm.add_ri(RSP, total)

        if ins.dst is not None:
            self._store_value(ins.dst, RAX)
            
    def _gen_console_builtin(self, ins: I.Call) -> None:
        name = ins.target

        if name in ("console.print", "console.eprint"):
            if len(ins.args) != 1:
                raise LoomError(f"{name} expects 1 argument",
                                self.filename, ins.line, ins.col)
            fd = 2 if name == "console.eprint" else 1

            self._asm.sub_ri(RSP, SHADOW)
            self._load_value(ins.args[0], RCX)
            self._asm.mov_rr(RBX, RCX)

            self._asm.mov_rr(RCX, RBX)
            self._asm.call_extern("strlen")
            self.extern_symbols.add("strlen")

            self._asm.mov_rr(R8, RAX)
            self._asm.mov_rr(RDX, RBX)
            self._asm.mov_ri32(RCX, fd)

            self._asm.call_extern("_write")
            self.extern_symbols.add("_write")

            self._asm.add_ri(RSP, SHADOW)
            if ins.dst is not None:
                self._store_value(ins.dst, RAX)
            return

        if name in ("console.print_int", "console.eprint_int"):
            if len(ins.args) != 1:
                raise LoomError(f"{name} expects 1 argument",
                                self.filename, ins.line, ins.col)
            fd = 2 if name == "console.eprint_int" else 1
            self._asm.sub_ri(RSP, SHADOW)
            self._load_value(ins.args[0], RCX)
            self._asm.mov_ri32(RDX, fd)
            self._asm.call_extern("loom_print_int_rt")
            self.extern_symbols.add("loom_print_int_rt")
            self._asm.add_ri(RSP, SHADOW)
            if ins.dst is not None:
                self._store_value(ins.dst, RAX)
            return

        if name == "console.print_char":
            if len(ins.args) != 1:
                raise LoomError("console.print_char expects 1 argument",
                                self.filename, ins.line, ins.col)

            self._asm.sub_ri(RSP, 16 + SHADOW)
            self._load_value(ins.args[0], RAX)
            self._asm.mov_mr8(RSP, SHADOW, RAX)

            self._asm.mov_ri32(RCX, 1)
            self._asm.mov_rr(RDX, RSP)
            self._asm.add_ri(RDX, SHADOW)
            self._asm.mov_ri32(R8, 1)

            self._asm.call_extern("_write")
            self.extern_symbols.add("_write")

            self._asm.add_ri(RSP, 16 + SHADOW)
            if ins.dst is not None:
                self._store_value(ins.dst, RAX)
            return

        raise LoomError(
            f"codegen: console builtin {name!r} not implemented",
            self.filename, ins.line, ins.col
        )
        
    def _gen_alloc(self, ins: I.Alloc) -> None:
        self._asm.sub_ri(RSP, SHADOW)
        self._load_value(ins.size, RCX)
        self._asm.call_extern("malloc")
        self.extern_symbols.add("malloc")
        self._asm.add_ri(RSP, SHADOW)
        self._store_value(ins.dst, RAX)

    def _gen_free(self, ins: I.Free) -> None:
        self._asm.sub_ri(RSP, SHADOW)
        self._load_value(ins.ptr, RCX)
        self._asm.call_extern("free")
        self.extern_symbols.add("free")
        self._asm.add_ri(RSP, SHADOW)