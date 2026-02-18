from __future__ import annotations

from dataclasses import dataclass


NAG_LINES = {
    "unknown_char": "Arre bhai, yeh character kya hai? Keyboard pe stunt mat karo.",
    "unterminated_string": "Quote khola hai toh band bhi karo, warna compiler ro dega.",
    "expected_start": "Program start hi bhool gaya? `shuru` daal na bhai.",
    "expected_end": "Scene close karna tha. `bass` ke bina compiler nahi rukega.",
    "missing_semicolon": "Semicolon kidhar gaya bhai? Line ka scene toot gaya.",
    "missing_lparen": "Bracket kholna tha bhai. `(` missing hai.",
    "missing_rparen": "Bracket bandh karo bhai. `)` missing hai.",
    "missing_lbrace": "Block start ke liye `{` chahiye, hawa mein code mat udao.",
    "missing_rbrace": "Block bandh karo `{...}` ka balance bigad gaya.",
    "invalid_statement": "Yeh statement ka scene samajh nahi aaya. Syntax theek karo.",
    "invalid_expression": "Expression ulta-pulta hai. Thoda seedha likh, bhai.",
    "unexpected_token": "Token ka scene off hai. Jo expected tha woh nahi mila.",
    "undeclared_variable": "Variable hawa mein bana diya kya? Pehle declare karo.",
    "redeclared_variable": "Same variable do baar? Itna bhi overconfidence theek nahi.",
    "type_mismatch": "Type mismatch ho gaya. Maths aur mood alag chal rahe hain.",
    "invalid_condition": "Condition ka logic weak hai. Bool/int mein baat kar bhai.",
    "return_type": "Return ka scene mismatch hai. Function type check kar.",
    "undeclared_function": "Function ka naam suna nahi bhai. Pehle define kar.",
    "arity_mismatch": "Arguments ka count ulta hai. Function ko jitna chahiye utna bhej.",
    "invalid_params": "Function params ka syntax scene off hai.",
    "invalid_function": "Function declaration ka format toot gaya.",
    "break_outside_loop": "`tod` loop/switch ke bahar kaise chal raha hai bhai?",
    "continue_outside_loop": "`jari` bhi loop ke bahar nahi chalega.",
    "unknown_type": "Type ka naam compiler ko nahi mila.",
    "invalid_lvalue": "Assignment ke left side pe valid target do.",
    "array_init_not_supported": "Array init short syntax abhi support nahi hai.",
    "duplicate_default": "Switch mein ek hi `default` hota hai, extra mat daalo bhai.",
    "invalid_case_label": "Case label constant int/bool hona chahiye, random mat likho.",
    "duplicate_case": "Same case value repeat kiya hai. Switch ka map clean rakho.",
    "missing_import": "Import file missing hai bhai. Path check karo.",
    "circular_import": "Import chain gol-gol ghoom rahi hai. Circular dependency hatao.",
    "module_has_main": "Imported module library hona chahiye, usme main statements mat rakho.",
}


def nag_line(code: str) -> str:
    return NAG_LINES.get(code, "Compiler confuse ho gaya bhai. Thoda code saaf likh.")


@dataclass
class PatakhaWarning:
    code: str
    message: str
    line: int
    column: int

    def pretty(self, source_name: str | None = None) -> str:
        prefix = f"{source_name}:" if source_name else ""
        return f"{prefix}{self.line}:{self.column} [warning:{self.code}] {self.message}"


@dataclass
class PatakhaError(Exception):
    code: str
    technical: str
    line: int
    column: int

    @property
    def nag(self) -> str:
        return nag_line(self.code)

    def pretty(self, source_name: str | None = None, source_text: str | None = None) -> str:
        prefix = f"{source_name}:" if source_name else ""
        base = (
            f"{prefix}{self.line}:{self.column} [{self.code}] {self.technical}\n"
            f"  {self.nag}"
        )
        frame = _source_frame(source_text, self.line, self.column)
        if frame:
            return f"{base}\n{frame}"
        return base

    def __str__(self) -> str:
        return self.pretty()


@dataclass
class PatakhaAggregateError(Exception):
    errors: list[PatakhaError]

    def pretty(self, source_name: str | None = None, source_text: str | None = None) -> str:
        return "\n".join(err.pretty(source_name, source_text=source_text) for err in self.errors)

    def __str__(self) -> str:
        return self.pretty()


def _source_frame(source_text: str | None, line: int, column: int) -> str:
    if not source_text:
        return ""
    lines = source_text.splitlines()
    if line < 1 or line > len(lines):
        return ""
    content = lines[line - 1]
    caret_pos = max(column, 1)
    caret_line = " " * (caret_pos - 1) + "^"
    return f"  | {content}\n  | {caret_line}"
