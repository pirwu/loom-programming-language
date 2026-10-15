"""
Writer PE/COFF relocatable object (.obj) for Windows x86-64.
"""

from __future__ import annotations

import struct

IMAGE_FILE_MACHINE_AMD64 = 0x8664
IMAGE_FILE_LINK_ONCE     = 0x0800

IMAGE_SCN_CNT_CODE               = 0x00000020
IMAGE_SCN_CNT_INITIALIZED_DATA   = 0x00000040
IMAGE_SCN_MEM_EXECUTE            = 0x20000000
IMAGE_SCN_MEM_READ               = 0x40000000
IMAGE_SCN_MEM_WRITE              = 0x80000000
IMAGE_SCN_LNK_INFO               = 0x00000200
IMAGE_SCN_LNK_REMOVE             = 0x00000800

IMAGE_SYM_CLASS_EXTERNAL = 2
IMAGE_SYM_CLASS_STATIC   = 3

IMAGE_SYM_TYPE_NULL = 0
IMAGE_SYM_DTYPE_FUNCTION = 2

IMAGE_REL_AMD64_ADDR64 = 0x0001
IMAGE_REL_AMD64_ADDR32 = 0x0002
IMAGE_REL_AMD64_REL32  = 0x0004
IMAGE_REL_AMD64_REL32_5 = 0x0009

IMAGE_SYM_UNDEFINED = 0

def _pad4(n: int) -> int:
    return (4 - (n % 4)) % 4

class _StrTab:
    def __init__(self) -> None:
        self._content = bytearray()
        self._cache: dict[str, int] = {}

    def add(self, s: str) -> int:
        if s in self._cache:
            return self._cache[s]
        off = 4 + len(self._content)
        self._content.extend(s.encode("ascii"))
        self._content.append(0)
        self._cache[s] = off
        return off

    def to_bytes(self) -> bytes:
        size = 4 + len(self._content)
        return struct.pack("<I", size) + bytes(self._content)

    def sym_name(self, s: str) -> bytes:
        if len(s) <= 8:
            return s.encode("ascii").ljust(8, b"\x00")
        off = self.add(s)
        return struct.pack("<II", 0, off)

    def section_name(self, s: str) -> bytes:
        return s.encode("ascii").ljust(8, b"\x00")[:8]

def build_object(
    text: bytes,
    rodata: bytes,
    data: bytes,
    functions: dict[str, int],
    data_symbols: dict[str, int],
    externs: list[str],
    relocs: list[tuple[int, str, object]],
) -> bytes:
    strtab = _StrTab()

    extern_set = set(externs)
    for _, kind, payload in relocs:
        if kind == "extern":
            extern_set.add(str(payload))
        elif kind == "local":
            n = str(payload)
            if n not in functions and n not in data_symbols:
                extern_set.add(n)
    externs_sorted = sorted(extern_set)

    symbols: list[tuple[str, int, int, int, int]] = []
    sym_index: dict[str, int] = {}

    def add_symbol(name: str, value: int, section_number: int,
                   type_: int, storage_class: int) -> int:
        idx = len(symbols)
        symbols.append((name, value, section_number, type_, storage_class))
        if name:
            sym_index[name] = idx
        return idx

    FUNC_TYPE = IMAGE_SYM_DTYPE_FUNCTION << 8
    OBJ_TYPE = 0

    text_sec_num   = 1
    rodata_sec_num = 2
    data_sec_num   = 3

    add_symbol(".file", 0, -2, 0, IMAGE_SYM_CLASS_STATIC)
    add_symbol(".text", 0, text_sec_num, 0, IMAGE_SYM_CLASS_STATIC)
    add_symbol(".rodata", 0, rodata_sec_num, 0, IMAGE_SYM_CLASS_STATIC)
    add_symbol(".data", 0, data_sec_num, 0, IMAGE_SYM_CLASS_STATIC)

    for fname, foff in functions.items():
        add_symbol(fname, foff, text_sec_num,
                   FUNC_TYPE, IMAGE_SYM_CLASS_EXTERNAL)

    for gname, goff in data_symbols.items():
        add_symbol(gname, goff, data_sec_num,
                   OBJ_TYPE, IMAGE_SYM_CLASS_EXTERNAL)

    for ename in externs_sorted:
        add_symbol(ename, 0, IMAGE_SYM_UNDEFINED, 0, IMAGE_SYM_CLASS_EXTERNAL)

    section_relocs: dict[int, list[tuple[int, int, int]]] = {1: [], 2: [], 3: []}

    def resolve_sym(name: str) -> int:
        if name in sym_index:
            return sym_index[name]
        return add_symbol(name, 0, IMAGE_SYM_UNDEFINED,
                          0, IMAGE_SYM_CLASS_EXTERNAL)

    for off, kind, payload in relocs:
        if kind == "rodata":
            sym_idx = sym_index.get(".rodata", 0)
            section_relocs[1].append((off, sym_idx, IMAGE_REL_AMD64_REL32))
        elif kind == "extern":
            sym_idx = resolve_sym(str(payload))
            section_relocs[1].append((off, sym_idx, IMAGE_REL_AMD64_REL32))
        elif kind == "local":
            name = str(payload)
            if name in sym_index:
                sym_idx = sym_index[name]
            else:
                sym_idx = resolve_sym(name)
            section_relocs[1].append((off, sym_idx, IMAGE_REL_AMD64_REL32))
        else:
            raise ValueError(f"unknown reloc kind {kind!r}")

    symtab = bytearray()
    for name, value, sec_num, type_, storage in symbols:
        name_bytes = strtab.sym_name(name)
        symtab.extend(name_bytes)
        symtab.extend(struct.pack("<I", value))
        symtab.extend(struct.pack("<h", sec_num))
        symtab.extend(struct.pack("<H", type_))
        symtab.extend(struct.pack("<B", storage))
        symtab.extend(struct.pack("<B", 0))

    text_reloc_data = bytearray()
    for off, sym_idx, rtype in section_relocs[1]:
        text_reloc_data.extend(struct.pack("<IIH", off, sym_idx, rtype))

    text_padded   = text + b"\x00" * _pad4(len(text))
    rodata_padded = rodata + b"\x00" * _pad4(len(rodata))
    data_padded   = data + b"\x00" * _pad4(len(data))

    num_sections = 3
    header_size = 20
    section_hdr_size = 40
    headers_size = header_size + num_sections * section_hdr_size

    off_text_data   = headers_size
    off_text_reloc  = off_text_data + len(text_padded)
    off_rodata_data = off_text_reloc + len(text_reloc_data)
    off_data_data   = off_rodata_data + len(rodata_padded)
    off_symtab      = off_data_data + len(data_padded)

    strtab_data = strtab.to_bytes()

    fh = struct.pack(
        "<HHIIIHH",
        IMAGE_FILE_MACHINE_AMD64,
        num_sections,
        0,
        off_symtab,
        len(symbols),
        0,
        0,
    )

    def section_header(name: bytes, vsize: int, vaddr: int, raw_size: int,
                       raw_ptr: int, reloc_ptr: int, num_relocs: int,
                       characteristics: int) -> bytes:
        return (
            name
            + struct.pack("<I", vsize)
            + struct.pack("<I", vaddr)
            + struct.pack("<I", raw_size)
            + struct.pack("<I", raw_ptr)
            + struct.pack("<I", reloc_ptr)
            + struct.pack("<I", 0)
            + struct.pack("<H", num_relocs)
            + struct.pack("<H", 0)
            + struct.pack("<I", characteristics)
        )

    text_hdr = section_header(
        strtab.section_name(".text"),
        len(text), 0, len(text_padded),
        off_text_data if len(text) > 0 else 0,
        off_text_reloc if len(text_reloc_data) > 0 else 0,
        len(section_relocs[1]),
        IMAGE_SCN_CNT_CODE | IMAGE_SCN_MEM_EXECUTE | IMAGE_SCN_MEM_READ,
    )

    rodata_hdr = section_header(
        strtab.section_name(".rodata"),
        len(rodata), 0, len(rodata_padded),
        off_rodata_data if len(rodata) > 0 else 0,
        0, 0,
        IMAGE_SCN_CNT_INITIALIZED_DATA | IMAGE_SCN_MEM_READ,
    )

    data_hdr = section_header(
        strtab.section_name(".data"),
        len(data), 0, len(data_padded),
        off_data_data if len(data) > 0 else 0,
        0, 0,
        IMAGE_SCN_CNT_INITIALIZED_DATA | IMAGE_SCN_MEM_READ | IMAGE_SCN_MEM_WRITE,
    )

    out = bytearray()
    out.extend(fh)
    out.extend(text_hdr)
    out.extend(rodata_hdr)
    out.extend(data_hdr)
    assert len(out) == off_text_data

    out.extend(text_padded)
    out.extend(text_reloc_data)
    out.extend(rodata_padded)
    out.extend(data_padded)
    out.extend(symtab)
    out.extend(strtab_data)

    return bytes(out)

    def add_symbol(name: str, value: int, section_number: int,
                   type_: int, storage_class: int) -> int:
        idx = len(symbols)
        symbols.append((name, value, section_number, type_, storage_class))
        if name:
            sym_index[name] = idx
        return idx

    FUNC_TYPE = IMAGE_SYM_DTYPE_FUNCTION << 8

    text_sec_num = 1
    rodata_sec_num = 2

    add_symbol(".file", 0, -2, 0, IMAGE_SYM_CLASS_STATIC)
    add_symbol(".text", 0, text_sec_num, 0, IMAGE_SYM_CLASS_STATIC)
    add_symbol(".rodata", 0, rodata_sec_num, 0, IMAGE_SYM_CLASS_STATIC)

    for fname, foff in functions.items():
        add_symbol(fname, foff, text_sec_num,
                   FUNC_TYPE, IMAGE_SYM_CLASS_EXTERNAL)

    for ename in externs_sorted:
        add_symbol(ename, 0, IMAGE_SYM_UNDEFINED, 0, IMAGE_SYM_CLASS_EXTERNAL)

    section_relocs: dict[int, list[tuple[int, int, int]]] = {1: [], 2: []}

    for off, kind, payload in relocs:
        if kind == "rodata":
            sym_idx = sym_index.get(".rodata", 0)
            section_relocs[1].append((off, sym_idx, IMAGE_REL_AMD64_REL32))
        elif kind == "extern":
            name = str(payload)
            sym_idx = sym_index.get(name)
            if sym_idx is None:
                sym_idx = add_symbol(name, 0, IMAGE_SYM_UNDEFINED,
                                     0, IMAGE_SYM_CLASS_EXTERNAL)
            section_relocs[1].append((off, sym_idx, IMAGE_REL_AMD64_REL32))
        elif kind == "local":
            name = str(payload)
            if name in sym_index:
                sym_idx = sym_index[name]
            else:
                sym_idx = add_symbol(name, 0, IMAGE_SYM_UNDEFINED,
                                     0, IMAGE_SYM_CLASS_EXTERNAL)
            section_relocs[1].append((off, sym_idx, IMAGE_REL_AMD64_REL32))
        else:
            raise ValueError(f"unknown reloc kind {kind!r}")

    symtab = bytearray()
    for name, value, sec_num, type_, storage in symbols:
        name_bytes = strtab.sym_name(name)
        symtab.extend(name_bytes)
        symtab.extend(struct.pack("<I", value))
        symtab.extend(struct.pack("<h", sec_num))
        symtab.extend(struct.pack("<H", type_))
        symtab.extend(struct.pack("<B", storage))
        symtab.extend(struct.pack("<B", 0))

    text_reloc_data = bytearray()
    for off, sym_idx, rtype in section_relocs[1]:
        text_reloc_data.extend(struct.pack("<IIH", off, sym_idx, rtype))

    text_padded = text + b"\x00" * _pad4(len(text))
    rodata_padded = rodata + b"\x00" * _pad4(len(rodata))

    num_sections = 2
    header_size = 20
    section_hdr_size = 40
    headers_size = header_size + num_sections * section_hdr_size

    off_text_data = headers_size
    off_text_reloc = off_text_data + len(text_padded)
    off_rodata_data = off_text_reloc + len(text_reloc_data)
    off_symtab = off_rodata_data + len(rodata_padded)

    strtab_data = strtab.to_bytes()
    off_strtab = off_symtab + len(symtab)

    fh = struct.pack(
        "<HHIIIHH",
        IMAGE_FILE_MACHINE_AMD64,
        num_sections,
        0,
        off_symtab,
        len(symbols),
        0,
        0,
    )

    def section_header(name: bytes, vsize: int, vaddr: int, raw_size: int,
                       raw_ptr: int, reloc_ptr: int, num_relocs: int,
                       characteristics: int) -> bytes:
        return (
            name
            + struct.pack("<I", vsize)
            + struct.pack("<I", vaddr)
            + struct.pack("<I", raw_size)
            + struct.pack("<I", raw_ptr)
            + struct.pack("<I", reloc_ptr)
            + struct.pack("<I", 0)
            + struct.pack("<H", num_relocs)
            + struct.pack("<H", 0)
            + struct.pack("<I", characteristics)
        )

    text_hdr = section_header(
        strtab.section_name(".text"),
        len(text), 0, len(text_padded),
        off_text_data if len(text) > 0 else 0,
        off_text_reloc if len(text_reloc_data) > 0 else 0,
        len(section_relocs[1]),
        IMAGE_SCN_CNT_CODE | IMAGE_SCN_MEM_EXECUTE | IMAGE_SCN_MEM_READ,
    )

    rodata_hdr = section_header(
        strtab.section_name(".rodata"),
        len(rodata), 0, len(rodata_padded),
        off_rodata_data if len(rodata) > 0 else 0,
        0, 0,
        IMAGE_SCN_CNT_INITIALIZED_DATA | IMAGE_SCN_MEM_READ,
    )

    out = bytearray()
    out.extend(fh)
    out.extend(text_hdr)
    out.extend(rodata_hdr)
    assert len(out) == off_text_data

    out.extend(text_padded)
    out.extend(text_reloc_data)
    out.extend(rodata_padded)
    out.extend(symtab)
    out.extend(strtab_data)

    return bytes(out)
    strtab = _StrTab()

    extern_set = set(externs)
    for _, kind, payload in relocs:
        if kind == "extern":
            extern_set.add(str(payload))
        elif kind == "local":
            n = str(payload)
            if n not in functions:
                extern_set.add(n)
    externs_sorted = sorted(extern_set)

    symbols: list[tuple[str, int, int, int, int]] = []
    sym_index: dict[str, int] = {}

    def add_symbol(name: str, value: int, section_number: int,
                   type_: int, storage_class: int) -> int:
        idx = len(symbols)
        symbols.append((name, value, section_number, type_, storage_class))
        if name:
            sym_index[name] = idx
        return idx

    text_sec_num = 1
    rodata_sec_num = 2

    add_symbol(".file", 0, -2, 0, IMAGE_SYM_CLASS_STATIC)
    add_symbol(".text", 0, text_sec_num, 0, IMAGE_SYM_CLASS_STATIC)
    add_symbol(".rodata", 0, rodata_sec_num, 0, IMAGE_SYM_CLASS_STATIC)

    for fname, foff in functions.items():
        add_symbol(fname, foff, text_sec_num,
                   IMAGE_SYM_DTYPE_FUNCTION, IMAGE_SYM_CLASS_EXTERNAL)

    for ename in externs_sorted:
        add_symbol(ename, 0, IMAGE_SYM_UNDEFINED, 0, IMAGE_SYM_CLASS_EXTERNAL)

    section_relocs: dict[int, list[tuple[int, int, int]]] = {1: [], 2: []}

    for off, kind, payload in relocs:
        if kind == "rodata":
            sym_idx = sym_index.get(".rodata", 0)
            section_relocs[1].append((off, sym_idx, IMAGE_REL_AMD64_REL32))
        elif kind == "extern":
            name = str(payload)
            sym_idx = sym_index.get(name)
            if sym_idx is None:
                sym_idx = add_symbol(name, 0, IMAGE_SYM_UNDEFINED,
                                     0, IMAGE_SYM_CLASS_EXTERNAL)
            section_relocs[1].append((off, sym_idx, IMAGE_REL_AMD64_REL32))
        elif kind == "local":
            name = str(payload)
            if name in sym_index:
                sym_idx = sym_index[name]
            else:
                sym_idx = add_symbol(name, 0, IMAGE_SYM_UNDEFINED,
                                     0, IMAGE_SYM_CLASS_EXTERNAL)
            section_relocs[1].append((off, sym_idx, IMAGE_REL_AMD64_REL32))
        else:
            raise ValueError(f"unknown reloc kind {kind!r}")

    symtab = bytearray()
    for name, value, sec_num, type_, storage in symbols:
        name_bytes = strtab.sym_name(name)
        symtab.extend(name_bytes)
        symtab.extend(struct.pack("<I", value))
        symtab.extend(struct.pack("<h", sec_num))
        symtab.extend(struct.pack("<H", type_))
        symtab.extend(struct.pack("<B", storage))
        symtab.extend(struct.pack("<B", 0))
    if len(symtab) % 4 != 0:
        symtab.extend(b"\x00" * _pad4(len(symtab)))

    text_reloc_data = bytearray()
    for off, sym_idx, rtype in section_relocs[1]:
        text_reloc_data.extend(struct.pack("<IIH", off, sym_idx, rtype))

    text_padded = text + b"\x00" * _pad4(len(text))
    rodata_padded = rodata + b"\x00" * _pad4(len(rodata))

    num_sections = 2
    header_size = 20
    section_hdr_size = 40
    headers_size = header_size + num_sections * section_hdr_size

    off_text_data = headers_size
    off_text_reloc = off_text_data + len(text_padded)
    off_rodata_data = off_text_reloc + len(text_reloc_data)
    off_symtab = off_rodata_data + len(rodata_padded)
    off_strtab = off_symtab + len(symtab)

    fh = struct.pack(
        "<HHIIIHH",
        IMAGE_FILE_MACHINE_AMD64,
        num_sections,
        0,
        off_symtab,
        len(symbols),
        0,
        0,
    )

    def section_header(name: bytes, vsize: int, vaddr: int, raw_size: int,
                       raw_ptr: int, reloc_ptr: int, num_relocs: int,
                       characteristics: int) -> bytes:
        return (
            name
            + struct.pack("<I", vsize)
            + struct.pack("<I", vaddr)
            + struct.pack("<I", raw_size)
            + struct.pack("<I", raw_ptr)
            + struct.pack("<I", reloc_ptr)
            + struct.pack("<I", 0)
            + struct.pack("<H", num_relocs)
            + struct.pack("<H", 0)
            + struct.pack("<I", characteristics)
        )

    text_hdr = section_header(
        strtab.section_name(".text"),
        len(text), 0, len(text_padded),
        off_text_data if len(text) > 0 else 0,
        off_text_reloc if len(text_reloc_data) > 0 else 0,
        len(section_relocs[1]),
        IMAGE_SCN_CNT_CODE | IMAGE_SCN_MEM_EXECUTE | IMAGE_SCN_MEM_READ,
    )

    rodata_hdr = section_header(
        strtab.section_name(".rodata"),
        len(rodata), 0, len(rodata_padded),
        off_rodata_data if len(rodata) > 0 else 0,
        0, 0,
        IMAGE_SCN_CNT_INITIALIZED_DATA | IMAGE_SCN_MEM_READ,
    )

    out = bytearray()
    out.extend(fh)
    out.extend(text_hdr)
    out.extend(rodata_hdr)
    assert len(out) == off_text_data

    out.extend(text_padded)
    out.extend(text_reloc_data)
    out.extend(rodata_padded)
    out.extend(symtab)
    out.extend(strtab.data)

    return bytes(out)