# BitTorrent Client (Portfolio Project)

Educational BitTorrent v1 client showcasing protocol work, concurrency, networking, and resilient file transfer patterns.

Included:
- `.torrent` parsing (bencode)
- HTTP + UDP tracker communication
- Peer handshake + wire messages
- Piece download and SHA-1 verification
- Multi-peer concurrent download
- Seeding support
- Basic DHT peer discovery
- Magnet link parsing

Usage:
```powershell
$env:PYTHONPATH = "bittorrent_client"
python -m btclient info .\path\file.torrent
python -m btclient download .\path\file.torrent .\downloads\output.bin
python -m btclient seed .\path\file.torrent .\downloads\output.bin
python -m btclient magnet "magnet:?xt=urn:btih:<hash>&tr=udp://tracker.example:80/announce"
```
