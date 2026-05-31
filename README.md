# TorrentEngine

Educational BitTorrent v1 client project focused on:
- Network programming
- Concurrent systems
- Protocol implementation
- File I/O
- Distributed systems concepts
- Real-world error handling

## Features
- `.torrent` parsing (bencode)
- HTTP/UDP tracker communication
- Peer handshake + wire messages
- Piece downloading + SHA-1 verification
- Multi-peer downloading
- Seeding support
- Basic DHT peer discovery
- Magnet link parsing

## Project Layout
- `pyproject.toml`
- `bittorrent_client/README.md`
- `bittorrent_client/btclient/`

## Quick Start
```powershell
cd bittorrent_client
$env:PYTHONPATH = "."
python -m btclient info .\path\file.torrent
python -m btclient download .\path\file.torrent .\downloads\output.bin
python -m btclient seed .\path\file.torrent .\downloads\output.bin
python -m btclient magnet "magnet:?xt=urn:btih:<hash>&tr=udp://tracker.example:80/announce"
```

## Notes
This is an educational implementation intended for protocol learning and portfolio demonstration.
Use only with content you are authorized to distribute.
