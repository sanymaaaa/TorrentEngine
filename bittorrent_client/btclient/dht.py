from __future__ import annotations

import asyncio
import os
import socket

from .bencode import bdecode, bencode
from .tracker import PeerAddress


class DHTClient:
    def __init__(self, node_id: bytes | None = None, bootstrap: list[tuple[str, int]] | None = None) -> None:
        self.node_id = node_id or os.urandom(20)
        self.bootstrap = bootstrap or [
            ("router.bittorrent.com", 6881),
            ("dht.transmissionbt.com", 6881),
            ("router.utorrent.com", 6881),
        ]

    async def get_peers(self, info_hash: bytes, timeout: float = 3.0) -> list[PeerAddress]:
        loop = asyncio.get_running_loop()
        found: list[PeerAddress] = []
        for host, port in self.bootstrap:
            tx = os.urandom(2)
            msg = {
                b"t": tx,
                b"y": b"q",
                b"q": b"get_peers",
                b"a": {b"id": self.node_id, b"info_hash": info_hash},
            }
            payload = bencode(msg)
            try:
                infos = await loop.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
                sockaddr = infos[0][4]
            except OSError:
                continue

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setblocking(False)
                await loop.sock_sendto(s, payload, sockaddr)
                try:
                    resp, _ = await asyncio.wait_for(loop.sock_recvfrom(s, 8192), timeout=timeout)
                except asyncio.TimeoutError:
                    continue

            try:
                data = bdecode(resp)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            r = data.get(b"r")
            if not isinstance(r, dict):
                continue
            values = r.get(b"values")
            if not isinstance(values, list):
                continue
            for v in values:
                if isinstance(v, bytes) and len(v) == 6:
                    ip = socket.inet_ntoa(v[:4])
                    p = int.from_bytes(v[4:], "big")
                    found.append(PeerAddress(ip, p))

        unique = {(p.ip, p.port): p for p in found}
        return list(unique.values())
