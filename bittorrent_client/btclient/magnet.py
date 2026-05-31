from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, quote, urlparse


@dataclass(slots=True)
class MagnetLink:
    info_hash: bytes
    display_name: str | None
    trackers: list[str]


class MagnetError(ValueError):
    pass


def parse_magnet(uri: str) -> MagnetLink:
    u = urlparse(uri)
    if u.scheme != "magnet":
        raise MagnetError("Not a magnet URI")
    q = parse_qs(u.query)
    xt_values = q.get("xt", [])
    info_hash = None
    for xt in xt_values:
        if xt.startswith("urn:btih:"):
            raw = xt.removeprefix("urn:btih:")
            if len(raw) == 40:
                info_hash = bytes.fromhex(raw)
                break
    if info_hash is None:
        raise MagnetError("Missing btih info hash")
    dn = q.get("dn", [None])[0]
    trackers = [t for t in q.get("tr", []) if t]
    return MagnetLink(info_hash=info_hash, display_name=dn, trackers=trackers)


def build_magnet(info_hash: bytes, name: str | None = None, trackers: list[str] | None = None) -> str:
    parts = ["xt=urn:btih:" + info_hash.hex()]
    if name:
        parts.append("dn=" + quote(name))
    for t in trackers or []:
        parts.append("tr=" + quote(t, safe=":/"))
    return "magnet:?" + "&".join(parts)
