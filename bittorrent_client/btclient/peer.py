from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass

from .tracker import PeerAddress

BT_PSTR = b"BitTorrent protocol"


@dataclass(slots=True)
class BlockRequest:
    index: int
    begin: int
    length: int


@dataclass(slots=True)
class PieceBlock:
    index: int
    begin: int
    data: bytes


class PeerProtocolError(RuntimeError):
    pass


class PeerConnection:
    def __init__(self, peer: PeerAddress, info_hash: bytes, peer_id: bytes, timeout: float = 8.0) -> None:
        self.peer = peer
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.timeout = timeout
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.peer_choking = True

    async def connect(self) -> None:
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection(self.peer.ip, self.peer.port), timeout=self.timeout
        )
        await self._send_handshake()
        await self._recv_handshake()
        await self.send_interested()

    async def close(self) -> None:
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

    async def _send_handshake(self) -> None:
        if not self.writer:
            raise PeerProtocolError("Writer unavailable")
        payload = struct.pack("!B", len(BT_PSTR)) + BT_PSTR + (b"\x00" * 8) + self.info_hash + self.peer_id
        self.writer.write(payload)
        await self.writer.drain()

    async def _recv_handshake(self) -> None:
        if not self.reader:
            raise PeerProtocolError("Reader unavailable")
        pstrlen = (await self.reader.readexactly(1))[0]
        pstr = await self.reader.readexactly(pstrlen)
        if pstr != BT_PSTR:
            raise PeerProtocolError("Unexpected protocol string")
        _reserved = await self.reader.readexactly(8)
        recv_info_hash = await self.reader.readexactly(20)
        _peer_id = await self.reader.readexactly(20)
        if recv_info_hash != self.info_hash:
            raise PeerProtocolError("Info hash mismatch")

    async def send_interested(self) -> None:
        await self._send_msg(2)

    async def _send_msg(self, msg_id: int, payload: bytes = b"") -> None:
        if not self.writer:
            raise PeerProtocolError("Writer unavailable")
        self.writer.write(struct.pack("!I", 1 + len(payload)) + struct.pack("!B", msg_id) + payload)
        await self.writer.drain()

    async def recv_message(self) -> tuple[int, bytes] | None:
        if not self.reader:
            raise PeerProtocolError("Reader unavailable")
        size = struct.unpack("!I", await self.reader.readexactly(4))[0]
        if size == 0:
            return None
        body = await self.reader.readexactly(size)
        return body[0], body[1:]

    async def wait_until_unchoked(self) -> None:
        while self.peer_choking:
            msg = await self.recv_message()
            if msg is None:
                continue
            msg_id, _payload = msg
            if msg_id == 1:
                self.peer_choking = False
            elif msg_id == 0:
                self.peer_choking = True

    async def request_block(self, req: BlockRequest) -> None:
        payload = struct.pack("!III", req.index, req.begin, req.length)
        await self._send_msg(6, payload)

    async def read_block(self) -> PieceBlock:
        while True:
            msg = await self.recv_message()
            if msg is None:
                continue
            msg_id, payload = msg
            if msg_id == 7 and len(payload) >= 8:
                index, begin = struct.unpack("!II", payload[:8])
                return PieceBlock(index=index, begin=begin, data=payload[8:])
            if msg_id == 0:
                self.peer_choking = True
            if msg_id == 1:
                self.peer_choking = False
