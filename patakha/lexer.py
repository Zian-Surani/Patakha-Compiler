from __future__ import annotations

from patakha.diagnostics import PatakhaError
from patakha.token import Token


KEYWORDS = {
    "import": "IMPORT",
    "laao": "IMPORT",
    "shuru": "START_BHAI",
    "bass": "BAS_KAR",
    # Backward-compatible aliases.
    "start_bhai": "START_BHAI",
    "bas_kar": "BAS_KAR",
    "bhai": "BHAI",
    "decimal": "DECIMAL",
    "float": "DECIMAL",
    "bool": "BOOL",
    "text": "TEXT",
    "khali": "VOID",
    "void": "VOID",
    "kaam": "KAAM",
    "agar": "AGAR",
    "warna": "WARNA",
    "tabtak": "JABTAK",
    "while": "JABTAK",
    "jabtak": "FOR",
    "bol": "BOL",
    "sach": "SACH",
    "jhooth": "JHOOTH",
    "nikal": "NIKAL",
    "for": "FOR",
    "kar": "DO",
    "do": "DO",
    "tod": "BREAK",
    "break": "BREAK",
    "jari": "CONTINUE",
    "continue": "CONTINUE",
    "switch": "SWITCH",
    "case": "CASE",
    "default": "DEFAULT",
    "struct": "STRUCT",
    "kaksha": "CLASS",
    "class": "CLASS",
}


TWO_CHAR_TOKENS = {
    "++": "INCR",
    "--": "DECR",
    "+=": "PLUS_ASSIGN",
    "-=": "MINUS_ASSIGN",
    "*=": "STAR_ASSIGN",
    "/=": "SLASH_ASSIGN",
    "%=": "MOD_ASSIGN",
    "==": "EQ",
    "!=": "NEQ",
    "<=": "LTE",
    ">=": "GTE",
    "&&": "AND",
    "||": "OR",
    "->": "ARROW",
}


ONE_CHAR_TOKENS = {
    "+": "PLUS",
    "-": "MINUS",
    "*": "STAR",
    "/": "SLASH",
    "%": "MOD",
    "=": "ASSIGN",
    "<": "LT",
    ">": "GT",
    "!": "NOT",
    "(": "LPAREN",
    ")": "RPAREN",
    "{": "LBRACE",
    "}": "RBRACE",
    "[": "LBRACKET",
    "]": "RBRACKET",
    ";": "SEMICOLON",
    ",": "COMMA",
    ".": "DOT",
    ":": "COLON",
}


class Lexer:
    def __init__(self, source: str) -> None:
        self.source = source
        self.length = len(source)
        self.index = 0
        self.line = 1
        self.column = 1

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []

        while not self._is_at_end():
            ch = self._peek()

            if ch in (" ", "\t", "\r", "\ufeff"):
                self._advance()
                continue
            if ch == "\n":
                self._advance_line()
                continue
            if ch == "/" and self._peek_next() == "/":
                self._skip_line_comment()
                continue
            if ch == "/" and self._peek_next() == "*":
                self._skip_block_comment()
                continue
            if ch.isalpha() or ch == "_":
                tokens.append(self._identifier())
                continue
            if ch.isdigit():
                tokens.append(self._number())
                continue
            if ch == '"':
                tokens.append(self._string())
                continue

            two = ch + self._peek_next()
            if two in TWO_CHAR_TOKENS:
                line, col = self.line, self.column
                self._advance()
                self._advance()
                tokens.append(Token(TWO_CHAR_TOKENS[two], two, line, col))
                continue

            if ch in ONE_CHAR_TOKENS:
                line, col = self.line, self.column
                self._advance()
                tokens.append(Token(ONE_CHAR_TOKENS[ch], ch, line, col))
                continue

            raise PatakhaError(
                code="unknown_char",
                technical=f"Unknown character: {ch!r}",
                line=self.line,
                column=self.column,
            )

        tokens.append(Token("EOF", "", self.line, self.column))
        return tokens

    def _identifier(self) -> Token:
        line, col = self.line, self.column
        start = self.index
        while not self._is_at_end():
            ch = self._peek()
            if not (ch.isalnum() or ch == "_"):
                break
            self._advance()

        text = self.source[start:self.index]
        kind = KEYWORDS.get(text, "IDENT")
        return Token(kind, text, line, col)

    def _number(self) -> Token:
        line, col = self.line, self.column
        start = self.index
        while not self._is_at_end() and self._peek().isdigit():
            self._advance()
        is_float = False
        if (
            not self._is_at_end()
            and self._peek() == "."
            and self.index + 1 < self.length
            and self.source[self.index + 1].isdigit()
        ):
            is_float = True
            self._advance()
            while not self._is_at_end() and self._peek().isdigit():
                self._advance()
        text = self.source[start:self.index]
        if is_float:
            return Token("FLOAT", float(text), line, col)
        return Token("NUMBER", int(text), line, col)

    def _string(self) -> Token:
        line, col = self.line, self.column
        self._advance()
        chars: list[str] = []
        while not self._is_at_end() and self._peek() != '"':
            ch = self._peek()
            if ch == "\n":
                raise PatakhaError(
                    code="unterminated_string",
                    technical="Unterminated string literal",
                    line=line,
                    column=col,
                )
            if ch == "\\":
                self._advance()
                if self._is_at_end():
                    break
                esc = self._peek()
                escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
                chars.append(escapes.get(esc, esc))
                self._advance()
                continue
            chars.append(ch)
            self._advance()

        if self._is_at_end() or self._peek() != '"':
            raise PatakhaError(
                code="unterminated_string",
                technical="Unterminated string literal",
                line=line,
                column=col,
            )
        self._advance()
        return Token("STRING", "".join(chars), line, col)

    def _skip_line_comment(self) -> None:
        while not self._is_at_end() and self._peek() != "\n":
            self._advance()

    def _skip_block_comment(self) -> None:
        self._advance()
        self._advance()
        while not self._is_at_end():
            if self._peek() == "*" and self._peek_next() == "/":
                self._advance()
                self._advance()
                return
            if self._peek() == "\n":
                self._advance_line()
            else:
                self._advance()
        raise PatakhaError(
            code="unterminated_string",
            technical="Unterminated block comment",
            line=self.line,
            column=self.column,
        )

    def _is_at_end(self) -> bool:
        return self.index >= self.length

    def _peek(self) -> str:
        return self.source[self.index]

    def _peek_next(self) -> str:
        if self.index + 1 >= self.length:
            return "\0"
        return self.source[self.index + 1]

    def _advance(self) -> str:
        ch = self.source[self.index]
        self.index += 1
        self.column += 1
        return ch

    def _advance_line(self) -> None:
        self.index += 1
        self.line += 1
        self.column = 1
