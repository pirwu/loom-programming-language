from core.lexer import lex
from core.parser import Parser
from core.utils import print_ast

if __name__ == '__main__':
    code = open('test.loom', 'r').read()

    tokens = lex(code) # лексер
    parser = Parser(tokens) # парсер
    ast = parser.parse() # ast дерево

    print_ast(ast)