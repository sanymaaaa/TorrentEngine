from __future__ import annotations

import argparse
import asyncio

from .client import TorrentClient
from .magnet import parse_magnet
from .torrent import parse_torrent


def main() -> None:
    parser = argparse.ArgumentParser(description="Educational BitTorrent client")
    sub = parser.add_subparsers(dest="cmd", required=True)

    dl = sub.add_parser("download", help="Download from .torrent")
    dl.add_argument("torrent")
    dl.add_argument("output")
    dl.add_argument("--port", type=int, default=6889)

    sd = sub.add_parser("seed", help="Seed an existing file")
    sd.add_argument("torrent")
    sd.add_argument("data")
    sd.add_argument("--port", type=int, default=6889)

    mg = sub.add_parser("magnet", help="Parse magnet link")
    mg.add_argument("uri")

    info = sub.add_parser("info", help="Inspect .torrent metadata")
    info.add_argument("torrent")

    args = parser.parse_args()

    if args.cmd == "magnet":
        m = parse_magnet(args.uri)
        print(f"info_hash={m.info_hash.hex()}")
        print(f"display_name={m.display_name}")
        print("trackers=")
        for t in m.trackers:
            print(f"  - {t}")
        return

    if args.cmd == "info":
        t = parse_torrent(args.torrent)
        print(f"name={t.name}")
        print(f"size={t.length}")
        print(f"pieces={len(t.pieces)}")
        print(f"piece_length={t.piece_length}")
        print(f"info_hash={t.info_hash.hex()}")
        print("trackers=")
        for tr in t.announce_list:
            print(f"  - {tr}")
        return

    client = TorrentClient(listen_port=args.port)
    if args.cmd == "download":
        stats = asyncio.run(client.download_torrent(args.torrent, args.output))
        print(
            f"download complete: {stats.completed_pieces}/{stats.total_pieces} pieces, {stats.downloaded_bytes} bytes"
        )
    elif args.cmd == "seed":
        asyncio.run(client.seed(args.torrent, args.data))


if __name__ == "__main__":
    main()
