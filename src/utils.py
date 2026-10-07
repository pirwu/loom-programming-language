from core.ast import (
    LoomAssign,
    LoomBinOp,
    LoomConsole,
    LoomNumber,
    LoomProgram,
    LoomVariable
)

def print_ast(node, indent=0):
    prefix = '  ' * indent

    match node:
        case LoomProgram(statements):
            print(f'{prefix}LoomProgram')
            for stmt in statements:
                print_ast(stmt, indent + 1)

        case LoomAssign(name, expr):
            print(f'{prefix}LoomAssign {name}')
            print_ast(expr, indent + 1)

        case LoomConsole(expr):
            print(f'{prefix}LoomConsole')
            print_ast(expr, indent + 1)

        case LoomBinOp(left, op, right):
            print(f'{prefix}LoomBinOp {op}')
            print_ast(left, indent + 1)
            print_ast(right, indent + 1)

        case LoomNumber(value):
            print(f'{prefix}LoomNumber {value}')

        case LoomVariable(name):
            print(f'{prefix}LoomVariable {name}')

        case _:
            print(f'{prefix}Unknown node: {node}')
