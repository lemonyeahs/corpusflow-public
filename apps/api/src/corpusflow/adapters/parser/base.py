from dataclasses import dataclass
from typing import Any, Protocol


class ParserError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ParsedSection:
    title: str
    text: str
    location: dict[str, Any]


@dataclass(frozen=True)
class ParseResult:
    parser: str
    parser_version: str
    text: str
    markdown: str
    structured: dict[str, Any]
    sections: list[ParsedSection]
    input_sha256: str
    input_bytes: int


class ParserAdapter(Protocol):
    name: str
    version: str

    def parse(self, content: bytes, filename: str, media_type: str) -> ParseResult: ...
