from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PieceSpan:
    index: int
    size: int
    offset: int


class PieceStore:
    def __init__(self, path: str | Path, total_length: int, piece_length: int, piece_hashes: list[bytes]):
        self.path = Path(path)
        self.total_length = total_length
        self.piece_length = piece_length
        self.piece_hashes = piece_hashes
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size != total_length:
            with self.path.open("wb") as f:
                if total_length > 0:
                    f.seek(total_length - 1)
                    f.write(b"\0")

    def piece_span(self, index: int) -> PieceSpan:
        offset = index * self.piece_length
        remaining = self.total_length - offset
        size = min(self.piece_length, remaining)
        return PieceSpan(index=index, size=size, offset=offset)

    def verify_piece(self, index: int, data: bytes) -> bool:
        return hashlib.sha1(data).digest() == self.piece_hashes[index]

    def write_piece(self, index: int, data: bytes) -> None:
        span = self.piece_span(index)
        if len(data) != span.size:
            raise ValueError(f"Piece {index} has wrong size {len(data)} != {span.size}")
        if not self.verify_piece(index, data):
            raise ValueError(f"Piece {index} SHA-1 verification failed")
        with self.path.open("r+b") as f:
            f.seek(span.offset)
            f.write(data)

    def read_piece(self, index: int) -> bytes:
        span = self.piece_span(index)
        with self.path.open("rb") as f:
            f.seek(span.offset)
            return f.read(span.size)
