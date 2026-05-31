from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .bencode import bdecode, bencode


@dataclass(slots=True)
class TorrentMeta:
    announce: str | None
    announce_list: list[str]
    name: str
    piece_length: int
    pieces: list[bytes]
    length: int
    info_hash: bytes
    info_bytes: bytes


class TorrentFormatError(ValueError):
    pass


def parse_torrent(path: str | Path) -> TorrentMeta:
    payload = Path(path).read_bytes()
    root = bdecode(payload)
    if not isinstance(root, dict):
        raise TorrentFormatError("Torrent root must be a dictionary")

    info = root.get(b"info")
    if not isinstance(info, dict):
        raise TorrentFormatError("Missing info dictionary")

    info_bytes = bencode(info)
    info_hash = hashlib.sha1(info_bytes).digest()

    raw_pieces = info.get(b"pieces")
    if not isinstance(raw_pieces, bytes) or len(raw_pieces) % 20 != 0:
        raise TorrentFormatError("Invalid pieces field")
    pieces = [raw_pieces[i : i + 20] for i in range(0, len(raw_pieces), 20)]

    length = info.get(b"length")
    if not isinstance(length, int):
        raise TorrentFormatError("Only single-file torrents are currently supported")

    announce = _maybe_text(root.get(b"announce"))
    announce_list = []
    al = root.get(b"announce-list")
    if isinstance(al, list):
        for tier in al:
            if isinstance(tier, list):
                for url in tier:
                    text = _maybe_text(url)
                    if text:
                        announce_list.append(text)

    if announce and announce not in announce_list:
        announce_list.insert(0, announce)

    return TorrentMeta(
        announce=announce,
        announce_list=announce_list,
        name=_require_text(info.get(b"name"), "info.name"),
        piece_length=_require_int(info.get(b"piece length"), "info.piece length"),
        pieces=pieces,
        length=length,
        info_hash=info_hash,
        info_bytes=info_bytes,
    )


def _maybe_text(v: object) -> str | None:
    if isinstance(v, bytes):
        return v.decode(errors="replace")
    if isinstance(v, str):
        return v
    return None


def _require_text(v: object, field: str) -> str:
    txt = _maybe_text(v)
    if not txt:
        raise TorrentFormatError(f"Missing or invalid {field}")
    return txt


def _require_int(v: object, field: str) -> int:
    if not isinstance(v, int):
        raise TorrentFormatError(f"Missing or invalid {field}")
    return v
