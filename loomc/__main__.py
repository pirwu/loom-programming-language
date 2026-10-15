from __future__ import annotations

import os
import sys

from .errors import LoomError
from .lexer import Lexer

def _usage() -> str:
    return (
        "usage: python -m loomc <file.loom> [options]\n"
        "\n"
        "options:\n"
        "  --tokens          print tokens\n"
        "  --ast             print AST\n"
        "  --ir              print IR\n"
        "  -o <file>         name compile file (without .exe)\n"
        "  -c                only compile (.obj do not linked)\n"
        "  -S                print of the machine code in hex\n"
        "  -h, --help        this help\n"
    )

def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if not args or "-h" in args or "--help" in args:
        print(_usage(), file=sys.stderr if not args else sys.stdout)
        return 0 if args else 1

    mode = "compile"
    only_compile = False
    print_asm = False
    output: str | None = None
    input_paths: list[str] = []

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--tokens":
            mode = "tokens"
        elif a == "--ast":
            mode = "ast"
        elif a == "--ir":
            mode = "ir"
        elif a == "-c":
            only_compile = True
        elif a == "-S":
            print_asm = True
        elif a == "-o":
            i += 1
            if i >= len(args):
                print("loomc: -o want the argumnet", file=sys.stderr)
                return 1
            output = args[i]
        elif a.startswith("-"):
            print(f"loomc: do not understand this option {a}", file=sys.stderr)
            return 1
        else:
            input_paths.append(a)
        i += 1

    if not input_paths:
        print(_usage(), file=sys.stderr)
        return 1

    parsed_modules: list[tuple[str, "object"]] = [] 
    from .parser import Parser
    for path in input_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                src = f.read()
        except OSError as e:
            print(f"loomc: do not open {path}: {e}", file=sys.stderr)
            return 1

        try:
            tokens = Lexer(src, path).tokenize()
        except LoomError as e:
            print(e.format(), file=sys.stderr)
            return 1

        if mode == "tokens":
            print(f"=== {path} ===")
            for t in tokens:
                print(t)
            continue

        try:
            module_ast = Parser(tokens, path).parse_module()
        except LoomError as e:
            print(e.format(), file=sys.stderr)
            return 1

        if mode == "ast":
            print(f"=== {path} ===")
            from pprint import pprint
            pprint(module_ast)
            continue

        parsed_modules.append((path, module_ast))

    if mode in ("tokens", "ast"):
        return 0

    try:
        from .lower import Lower
        ir_module = Lower(input_paths).lower_all(parsed_modules)
    except LoomError as e:
        print(e.format(), file=sys.stderr)
        return 1

    if mode == "ir":
        from .ir_dump import dump_module
        print(dump_module(ir_module))
        return 0

    try:
        from .codegen import Codegen
        codegen = Codegen(ir_module, input_paths)
        obj_bytes = codegen.generate()
    except LoomError as e:
        print(e.format(), file=sys.stderr)
        return 1

    if print_asm:
        print(codegen.dump_asm())

    if output is None:
        output = "a"

    obj_path = output + ".obj"
    try:
        with open(obj_path, "wb") as f:
            f.write(obj_bytes)
    except OSError as e:
        print(f"loomc: do not wrote {obj_path}: {e}", file=sys.stderr)
        return 1

    if only_compile:
        return 0

    exe_path = output + ".exe"
    try:
        from .link import link
        link(obj_path, exe_path)
    except LoomError as e:
        print(e.format(), file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"loomc: {e}", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())