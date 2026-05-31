from __future__ import annotations

import asyncio
import os
import random
import socket
import struct
from dataclasses import dataclass
from urllib.parse import quote_from_bytes, urlparse
from urllib.request import urlopen

from .bencode import bdecode


@dataclass(slots=True, frozen=True)
class PeerAddress:
    ip: str
    port: int


class TrackerError(RuntimeError):
    pass


def _parse_compact_peers(raw: bytes) -> list[PeerAddress]:
    if len(raw) % 6 != 0:
        return []
    out = []
    for i in range(0, len(raw), 6):
        ip = socket.inet_ntoa(raw[i : i + 4])
        port = struct.unpack("!H", raw[i + 4 : i + 6])[0]
        out.append(PeerAddress(ip, port))
    return out


async def announce_http(
    tracker_url: str,
    *,
    info_hash: bytes,
    peer_id: bytes,
    port: int,
    uploaded: int,
    downloaded: int,
    left: int,
    event: str | None,
    timeout: float = 8.0,
) -> list[PeerAddress]:
    def _do() -> list[PeerAddress]:
        params = {
            "info_hash": quote_from_bytes(info_hash),
            "peer_id": quote_from_bytes(peer_id),
            "port": str(port),
            "uploaded": str(uploaded),
            "downloaded": str(downloaded),
            "left": str(left),
            "compact": "1",
        }
        if event:
            params["event"] = event
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = tracker_url + ("&" if "?" in tracker_url else "?") + query
        with urlopen(url, timeout=timeout) as resp:
            payload = resp.read()
        data = bdecode(payload)
        if not isinstance(data, dict):
            raise TrackerError("Invalid HTTP tracker response")
        peers = data.get(b"peers")
        if isinstance(peers, bytes):
            return _parse_compact_peers(peers)
        return []

    return await asyncio.to_thread(_do)


async def announce_udp(
    tracker_url: str,
    *,
    info_hash: bytes,
    peer_id: bytes,
    port: int,
    uploaded: int,
    downloaded: int,
    left: int,
    event: int,
    timeout: float = 5.0,
) -> list[PeerAddress]:
    parsed = urlparse(tracker_url)
    host = parsed.hostname
    if not host or parsed.port is None:
        raise TrackerError("Invalid UDP tracker URL")

    loop = asyncio.get_running_loop()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setblocking(False)
        tx = random.randint(0, 2**31 - 1)
        connect_req = struct.pack("!QII", 0x41727101980, 0, tx)
        await loop.sock_sendto(s, connect_req, (host, parsed.port))
        data, _ = await asyncio.wait_for(loop.sock_recvfrom(s, 2048), timeout=timeout)
        if len(data) < 16:
            raise TrackerError("Short UDP connect response")
        action, rtx, conn_id = struct.unpack("!IIQ", data[:16])
        if action != 0 or rtx != tx:
            raise TrackerError("Invalid UDP connect response")

        tx2 = random.randint(0, 2**31 - 1)
        key = random.randint(0, 2**31 - 1)
        announce_req = struct.pack(
            "!QII20s20sQQQIIIiH",
            conn_id,
            1,
            tx2,
            info_hash,
            peer_id,
            downloaded,
            left,
            uploaded,
            event,
            0,
            key,
            -1,
            port,
        )
        await loop.sock_sendto(s, announce_req, (host, parsed.port))
        adata, _ = await asyncio.wait_for(loop.sock_recvfrom(s, 4096), timeout=timeout)

    if len(adata) < 20:
        raise TrackerError("Short UDP announce response")
    action, rtx, _interval, _leechers, _seeders = struct.unpack("!IIIII", adata[:20])
    if action != 1 or rtx != tx2:
        raise TrackerError("Invalid UDP announce response")
    return _parse_compact_peers(adata[20:])


async def announce_any(
    trackers: list[str],
    *,
    info_hash: bytes,
    peer_id: bytes,
    port: int,
    uploaded: int,
    downloaded: int,
    left: int,
    event: str | None,
) -> list[PeerAddress]:
    peers: list[PeerAddress] = []
    for url in trackers:
        try:
            if url.startswith("udp://"):
                evt = {None: 0, "completed": 1, "started": 2, "stopped": 3}[event]
                found = await announce_udp(
                    url,
                    info_hash=info_hash,
                    peer_id=peer_id,
                    port=port,
                    uploaded=uploaded,
                    downloaded=downloaded,
                    left=left,
                    event=evt,
                )
            elif url.startswith("http://") or url.startswith("https://"):
                found = await announce_http(
                    url,
                    info_hash=info_hash,
                    peer_id=peer_id,
                    port=port,
                    uploaded=uploaded,
                    downloaded=downloaded,
                    left=left,
                    event=event,
                )
            else:
                found = []
        except (TrackerError, OSError, asyncio.TimeoutError, ValueError):
            found = []
        peers.extend(found)
    unique = {(p.ip, p.port): p for p in peers}
    return list(unique.values())


def make_peer_id(prefix: bytes = b"-PC0001-") -> bytes:
    suffix = os.urandom(20 - len(prefix))
    return (prefix + suffix)[:20]
