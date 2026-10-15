from __future__ import annotations

import os
import shutil
import subprocess
import sys

from .errors import LoomError

CC_CANDIDATES = [
    "gcc", "cc", "clang",
    r"C:\msys64\ucrt64\bin\gcc.exe",
    r"C:\msys64\mingw64\bin\gcc.exe",
    r"C:\Program Files\mingw64\bin\gcc.exe",
    r"C:\Program Files (x86)\mingw64\bin\gcc.exe",
    r"C:\mingw64\bin\gcc.exe",
    r"C:\mingw32\bin\gcc.exe",
]

def _find_cc() -> str:
    for c in CC_CANDIDATES:
        if os.path.isabs(c):
            if os.path.exists(c):
                return c
        else:
            p = shutil.which(c)
            if p:
                return p
    raise FileNotFoundError(
        "MinGW gcc not found. Download MSYS2 or MinGW-w64 and add gcc in PATH."
    )

def _runtime_obj() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        base = os.path.dirname(here)

    rt_dir = os.path.join(base, "runtime")
    rt_c = os.path.join(rt_dir, "runtime.c")
    rt_o = os.path.join(rt_dir, "runtime.obj")

    if not os.path.exists(rt_c):
        raise LoomError(f"runtime.c not found: {rt_c}")

    need_build = True
    if os.path.exists(rt_o):
        if os.path.getmtime(rt_o) >= os.path.getmtime(rt_c):
            need_build = False

    if need_build:
        cc = _find_cc()
        cmd = [
            cc, "-c",
            "-O2",
            "-fno-stack-protector",
            "-fno-asynchronous-unwind-tables",
            rt_c, "-o", rt_o,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise LoomError(
                f"do not collect runtime.obj:\n{r.stderr.strip()}"
            )

    return rt_o

def link(obj_path: str, output_path: str) -> None:
    cc = _find_cc()
    rt = _runtime_obj()

    cmd = [
        cc,
        "-o", output_path,
        obj_path,
        rt,
        "-lkernel32",
        "-lmsvcrt",
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)

    if r.returncode != 0:
        msg = r.stderr.strip() or r.stdout.strip() or "link not succes"
        raise LoomError(msg)