from __future__ import annotations

import asyncio
import contextlib
import struct
from dataclasses import dataclass
from pathlib import Path

from .dht import DHTClient
from .peer import BlockRequest, PeerConnection
from .storage import PieceStore
from .torrent import TorrentMeta, parse_torrent
from .tracker import PeerAddress, announce_any, make_peer_id

BLOCK_SIZE = 16 * 1024


@dataclass(slots=True)
class DownloadStats:
    completed_pieces: int
    total_pieces: int
    downloaded_bytes: int


class TorrentClient:
    def __init__(self, listen_port: int = 6889, max_peers: int = 20) -> None:
        self.listen_port = listen_port
        self.max_peers = max_peers
        self.peer_id = make_peer_id()

    async def download_torrent(self, torrent_path: str | Path, output_path: str | Path) -> DownloadStats:
        meta = parse_torrent(torrent_path)
        return await self.download_from_meta(meta, output_path)

    async def download_from_meta(self, meta: TorrentMeta, output_path: str | Path) -> DownloadStats:
        store = PieceStore(output_path, meta.length, meta.piece_length, meta.pieces)
        dht = DHTClient()

        peers = await announce_any(
            meta.announce_list,
            info_hash=meta.info_hash,
            peer_id=self.peer_id,
            port=self.listen_port,
            uploaded=0,
            downloaded=0,
            left=meta.length,
            event="started",
        )
        peers.extend(await dht.get_peers(meta.info_hash))
        peer_map = {(p.ip, p.port): p for p in peers}
        all_peers = list(peer_map.values())[: self.max_peers]

        queue: asyncio.Queue[int] = asyncio.Queue()
        for idx in range(len(meta.pieces)):
            queue.put_nowait(idx)

        lock = asyncio.Lock()
        completed = set()
        downloaded = 0

        async def worker(peer: PeerAddress) -> None:
            nonlocal downloaded
            conn = PeerConnection(peer, meta.info_hash, self.peer_id)
            try:
                await conn.connect()
                await conn.wait_until_unchoked()
                while True:
                    piece = await queue.get()
                    if piece in completed:
                        queue.task_done()
                        continue
                    try:
                        blob = await self._download_piece(conn, store, piece)
                    except (asyncio.TimeoutError, OSError, ValueError):
                        queue.put_nowait(piece)
                        queue.task_done()
                        await asyncio.sleep(0.2)
                        continue

                    async with lock:
                        if piece not in completed:
                            store.write_piece(piece, blob)
                            completed.add(piece)
                            downloaded += len(blob)
                    queue.task_done()
                    if len(completed) == len(meta.pieces):
                        break
            except (asyncio.TimeoutError, OSError, ValueError):
                return
            finally:
                with contextlib.suppress(OSError, RuntimeError):
                    await conn.close()

        tasks = [asyncio.create_task(worker(p)) for p in all_peers]
        await queue.join()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        await announce_any(
            meta.announce_list,
            info_hash=meta.info_hash,
            peer_id=self.peer_id,
            port=self.listen_port,
            uploaded=0,
            downloaded=downloaded,
            left=max(0, meta.length - downloaded),
            event="completed" if len(completed) == len(meta.pieces) else None,
        )

        return DownloadStats(len(completed), len(meta.pieces), downloaded)

    async def _download_piece(self, conn: PeerConnection, store: PieceStore, piece_index: int) -> bytes:
        span = store.piece_span(piece_index)
        chunks: dict[int, bytes] = {}
        for begin in range(0, span.size, BLOCK_SIZE):
            length = min(BLOCK_SIZE, span.size - begin)
            await conn.request_block(BlockRequest(piece_index, begin, length))

        received = 0
        while received < span.size:
            block = await conn.read_block()
            if block.index != piece_index:
                continue
            if block.begin not in chunks:
                chunks[block.begin] = block.data
                received += len(block.data)

        assembled = b"".join(chunks[i] for i in sorted(chunks))
        if len(assembled) != span.size:
            raise ValueError("Piece assembly size mismatch")
        if not store.verify_piece(piece_index, assembled):
            raise ValueError("Piece SHA-1 mismatch")
        return assembled

    async def seed(self, torrent_path: str | Path, data_path: str | Path) -> None:
        meta = parse_torrent(torrent_path)
        store = PieceStore(data_path, meta.length, meta.piece_length, meta.pieces)

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                pstrlen = (await reader.readexactly(1))[0]
                pstr = await reader.readexactly(pstrlen)
                if pstr != b"BitTorrent protocol":
                    writer.close()
                    await writer.wait_closed()
                    return
                _reserved = await reader.readexactly(8)
                info_hash = await reader.readexactly(20)
                _peer_id = await reader.readexactly(20)
                if info_hash != meta.info_hash:
                    writer.close()
                    await writer.wait_closed()
                    return

                my_handshake = struct.pack("!B", 19) + b"BitTorrent protocol" + (b"\x00" * 8) + meta.info_hash + self.peer_id
                writer.write(my_handshake)
                writer.write(struct.pack("!IB", 1, 1))
                await writer.drain()

                while True:
                    size = struct.unpack("!I", await reader.readexactly(4))[0]
                    if size == 0:
                        continue
                    body = await reader.readexactly(size)
                    msg_id, payload = body[0], body[1:]
                    if msg_id == 6 and len(payload) == 12:
                        index, begin, length = struct.unpack("!III", payload)
                        piece = store.read_piece(index)
                        block = piece[begin : begin + length]
                        writer.write(struct.pack("!IBII", 9 + len(block), 7, index, begin) + block)
                        await writer.drain()
            except (asyncio.IncompleteReadError, ConnectionError, OSError, ValueError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handle, "0.0.0.0", self.listen_port)
        async with server:
            await announce_any(
                meta.announce_list,
                info_hash=meta.info_hash,
                peer_id=self.peer_id,
                port=self.listen_port,
                uploaded=0,
                downloaded=meta.length,
                left=0,
                event="started",
            )
            await server.serve_forever()
