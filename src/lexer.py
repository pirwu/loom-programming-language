"""Lexical analyzer for LOOM programming language"""

import re
from collections import namedtuple

Token = namedtuple('Token', ['type', 'value'])

KEYWORDS = {'console', 'LOOM'}

TOKEN_SPECIFICATION = [
    ('NUMBER', r'\d+(\.\d*)?'), # числа
    ('ID', r'[a-zA-Z_][a-zA-Z_0-9]*'), # идентификаторы (переменные)
    ('OP', r'[:]=|==|!=|<=|>=|[+\-*/=<>]'), # операции (присвоение и тд)
    ('SKIP', r'[ \t]+'), # пропускать пробелы и табуляции
    ('NEWLINE', r'\n'), # новая строка
    ('LPAREN', r'\('), # открывающая скобка
    ('RPAREN', r'\)'), # закрывающая скобка
    ('MISMATCH', r'.'), # всё остальное мисмач (несовпадение)
]


def lex(code):
    # компилируем все в один шаблон
    tok_regex = '|'.join(f'(?P<{name}>{pattern})' for name, pattern in TOKEN_SPECIFICATION)

    # разбиваем на токены
    for match in re.finditer(tok_regex, code):
        kind = match.lastgroup
        value = match.group()

        match kind:
            case 'NUMBER':
                yield Token(kind, float(value) if '.' in value else int(value))
            case 'ID':
                yield Token(value.upper() if value in KEYWORDS else 'ID', value)
            case 'NEWLINE' | 'SKIP':
                continue
            case 'LPAREN' | 'RPAREN' | 'OP':
                yield Token(kind, value)
            case 'MISMATCH':
                raise SyntaxError(f'Unexpected character: {value!r}')
