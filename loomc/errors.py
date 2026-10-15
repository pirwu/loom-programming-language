class LoomError(Exception):
    def __init__(self, message: str, filename: str = "<input>",
                 line: int = 0, col: int = 0):
        self.message = message
        self.filename = filename
        self.line = line
        self.col = col
        super().__init__(self.format())

    def format(self) -> str:
        if self.line:
            return f"{self.filename}:{self.line}:{self.col}: error: {self.message}"
        return f"{self.filename}: error: {self.message}"