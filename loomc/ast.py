"""AST LOOM v1."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Node:
    line: int = 0
    col: int = 0

@dataclass
class TypeRef(Node):
    name: str = ""
    inner: Optional["TypeRef"] = None
    array_len: Optional[int] = None


@dataclass
class Module(Node):
    name: str = ""
    imports: list[str] = field(default_factory=list)
    decls: list[Node] = field(default_factory=list)

@dataclass
class FnParam(Node):
    name: str = ""
    type: TypeRef = None 

@dataclass
class FnDecl(Node):
    name: str = ""
    params: list[FnParam] = field(default_factory=list)
    ret_type: Optional[TypeRef] = None
    body: Optional["Block"] = None
    is_export: bool = False
    is_extern: bool = False
    attrs: list[str] = field(default_factory=list)

@dataclass
class StructField(Node):
    name: str = ""
    type: TypeRef = None

@dataclass
class StructDecl(Node):
    name: str = ""
    fields: list[StructField] = field(default_factory=list)
    is_export: bool = False

@dataclass
class EnumVariant(Node):
    name: str = ""
    value: Optional[int] = None

@dataclass
class EnumDecl(Node):
    name: str = ""
    variants: list[EnumVariant] = field(default_factory=list)
    is_export: bool = False

@dataclass
class ConstDecl(Node):
    name: str = ""
    type: Optional[TypeRef] = None
    value: Node = None
    is_export: bool = False

@dataclass
class GlobalVarDecl(Node):
    name: str = ""
    type: TypeRef = None
    value: Optional[Node] = None
    is_export: bool = False

@dataclass
class Block(Node):
    stmts: list[Node] = field(default_factory=list)

@dataclass
class VarDecl(Node):
    name: str = ""
    type: TypeRef = None
    value: Optional[Node] = None

@dataclass
class Assign(Node):
    target: Node = None
    op: str = "="
    value: Node = None

@dataclass
class Ret(Node):
    value: Optional[Node] = None

@dataclass
class If(Node):
    cond: Node = None
    then_block: Block = None
    else_block: Optional[Block] = None

@dataclass
class While(Node):
    cond: Node = None
    body: Block = None
    
@dataclass
class Loop(Node):
    body: Block = None

@dataclass
class Break(Node):
    pass

@dataclass
class Continue(Node):
    pass

@dataclass
class Label(Node):
    name: str = ""

@dataclass
class Jmp(Node):
    label: str = ""

@dataclass
class ExprStmt(Node):
    expr: Node = None
    
@dataclass
class IntLit(Node):
    value: int = 0
    raw: str = ""

@dataclass
class FloatLit(Node):
    value: float = 0.0
    raw: str = ""

@dataclass
class StringLit(Node):
    value: str = ""

@dataclass
class CharLit(Node):
    value: str = ""

@dataclass
class BoolLit(Node):
    value: bool = False

@dataclass
class NullLit(Node):
    pass

@dataclass
class Ident(Node):
    name: str = ""

@dataclass
class BinOp(Node):
    op: str = ""
    left: Node = None
    right: Node = None

@dataclass
class UnOp(Node):
    op: str = ""
    operand: Node = None

@dataclass
class Call(Node):
    callee: Node = None
    args: list[Node] = field(default_factory=list)

@dataclass
class MemberAccess(Node):
    obj: Node = None
    field: str = ""

@dataclass
class Index(Node):
    obj: Node = None
    index: Node = None

@dataclass
class Cast(Node):
    expr: Node = None
    type: TypeRef = None

@dataclass
class Sizeof(Node):
    type: TypeRef = None