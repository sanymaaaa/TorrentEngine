from __future__ import annotations

from dataclasses import dataclass


class BencodeError(ValueError):
    pass


@dataclass(slots=True)
class DecodeResult:
    value: object
    offset: int


def bdecode(data: bytes) -> object:
    result = _decode_at(data, 0)
    if result.offset != len(data):
        raise BencodeError("Trailing bytes after valid bencode payload")
    return result.value


def _decode_at(data: bytes, i: int) -> DecodeResult:
    if i >= len(data):
        raise BencodeError("Unexpected end of input")
    token = data[i : i + 1]
    if token == b"i":
        end = data.index(b"e", i + 1)
        return DecodeResult(int(data[i + 1 : end]), end + 1)
    if token == b"l":
        items = []
        i += 1
        while data[i : i + 1] != b"e":
            result = _decode_at(data, i)
            items.append(result.value)
            i = result.offset
        return DecodeResult(items, i + 1)
    if token == b"d":
        i += 1
        dct = {}
        while data[i : i + 1] != b"e":
            k = _decode_at(data, i)
            v = _decode_at(data, k.offset)
            if not isinstance(k.value, bytes):
                raise BencodeError("Dictionary keys must be bytes")
            dct[k.value] = v.value
            i = v.offset
        return DecodeResult(dct, i + 1)
    if token.isdigit():
        colon = data.index(b":", i)
        size = int(data[i:colon])
        start = colon + 1
        end = start + size
        if end > len(data):
            raise BencodeError("String length exceeds input")
        return DecodeResult(data[start:end], end)
    raise BencodeError(f"Invalid bencode token at offset {i}")


def bencode(value: object) -> bytes:
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        raw = value.encode()
        return str(len(raw)).encode() + b":" + raw
    if isinstance(value, list):
        return b"l" + b"".join(bencode(v) for v in value) + b"e"
    if isinstance(value, dict):
        out = []
        for k in sorted(value.keys(), key=lambda x: x if isinstance(x, bytes) else str(x).encode()):
            key = k if isinstance(k, bytes) else str(k).encode()
            out.append(bencode(key))
            out.append(bencode(value[k]))
        return b"d" + b"".join(out) + b"e"
    raise TypeError(f"Unsupported type for bencode: {type(value)!r}")
