"""
IR LOOM v1.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Union

@dataclass
class Const:
    value: int
    is_string: bool = False
    def __repr__(self): return f"Const({self.value})"

@dataclass
class Temp:
    id: int
    def __repr__(self): return f"%t{self.id}"

@dataclass
class Var:
    name: str
    def __repr__(self): return f"%{self.name}"

@dataclass
class Global:
    name: str
    def __repr__(self): return f"@{self.name}"

@dataclass
class Label:
    name: str
    def __repr__(self): return f".{self.name}"

Value = Union[Const, Temp, Var, Global, Label]

@dataclass
class Instr:
    line: int = 0
    col: int = 0

@dataclass
class Mov(Instr):
    dst: Value = None
    src: Value = None

@dataclass
class BinOp(Instr):
    op: str = ""
    dst: Value = None
    a: Value = None
    b: Value = None

@dataclass
class Cmp(Instr):
    op: str = ""
    dst: Value = None
    a: Value = None
    b: Value = None

@dataclass
class UnOp(Instr):
    op: str = ""
    dst: Value = None
    a: Value = None

@dataclass
class Load(Instr):
    dst: Value = None
    addr: Value = None
    size: int = 8

@dataclass
class Store(Instr):
    addr: Value = None
    src: Value = None
    size: int = 8

@dataclass
class AddrOf(Instr):
    dst: Value = None
    var: Var | None = None

@dataclass
class LeaField(Instr):
    dst: Value = None
    base: Value = None
    offset: int = 0

@dataclass
class LeaIndex(Instr):
    dst: Value = None
    base: Value = None
    index: Value = None
    elem_size: int = 8

@dataclass
class Call(Instr):
    dst: Optional[Value] = None
    target: str = ""
    args: list[Value] = field(default_factory=list)
    is_extern: bool = False

@dataclass
class Syscall(Instr):
    dst: Optional[Value] = None
    nr: Value = None
    args: list[Value] = field(default_factory=list)

@dataclass
class Ret(Instr):
    value: Optional[Value] = None

@dataclass
class Jmp(Instr):
    target: str = ""

@dataclass
class JmpIf(Instr):
    cond: Value = None
    target: str = ""

@dataclass
class JmpIfZero(Instr):
    cond: Value = None
    target: str = ""

@dataclass
class LabelInstr(Instr):
    name: str = ""

@dataclass
class Alloc(Instr):
    dst: Value = None
    size: Value = None

@dataclass
class Free(Instr):
    ptr: Value = None

@dataclass
class IRParam:
    name: str
    size: int = 8

@dataclass
class IRFunction:
    name: str = ""
    params: list[IRParam] = field(default_factory=list)
    ret_size: int = 0       # 0 = void
    locals: list[IRParam] = field(default_factory=list)
    instrs: list[Instr] = field(default_factory=list)
    is_export: bool = False
    is_extern: bool = False

@dataclass
class IRGlobal:
    name: str
    size: int
    init: int | None = None

@dataclass
class IRModule:
    name: str = ""
    functions: list[IRFunction] = field(default_factory=list)
    globals: list[IRGlobal] = field(default_factory=list)
    strings: list[str] = field(default_factory=list)