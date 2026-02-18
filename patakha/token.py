from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    kind: str
    value: object
    line: int
    column: int

    def location(self) -> str:
        return f"{self.line}:{self.column}"

