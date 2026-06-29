#!/usr/bin/env python3
"""Generate a PCMU (G.711 mu-law) RTP stream pcap for SIPp's play_pcap_audio.

Self-contained: no dependency on system-provided SIPp media files. Produces an
EN10MB pcap of N RTP/UDP/IP/Ethernet packets spaced 20 ms apart (50 pkt/s). SIPp
extracts each UDP payload (the RTP packet) and replays it with this timing from
its own media socket, so this is enough to put real RTP on the wire for sngrep.

    python3 bench/media/gen_rtp_pcap.py [out.pcap]
    RTP_PACKETS=100 python3 bench/media/gen_rtp_pcap.py   # 100 * 20ms = 2s of audio
"""
import struct
import sys
import os

PACKETS = int(os.environ.get("RTP_PACKETS", "100"))   # 100 * 20ms = 2s
PTIME_US = 20000                                       # 20 ms packetization
PAYLOAD = 160                                          # PCMU bytes for 20ms @ 8kHz


def ip_checksum(hdr):
    s = 0
    for i in range(0, len(hdr), 2):
        s += (hdr[i] << 8) + hdr[i + 1]
    s = (s >> 16) + (s & 0xffff)
    s += (s >> 16)
    return (~s) & 0xffff


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "bench/media/rtp_pcmu.pcap"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "wb") as f:
        # pcap global header (little-endian), linktype 1 = EN10MB
        f.write(struct.pack("<IHHiIII", 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
        ssrc, seq, ts = 0x11223344, 0, 0
        for i in range(PACKETS):
            rtp = struct.pack("!BBHII", 0x80, 0x00, seq & 0xffff, ts & 0xffffffff, ssrc)
            rtp += bytes((i * 7 + j) & 0xff for j in range(PAYLOAD))   # filler audio
            udp = struct.pack("!HHHH", 40000, 40000, 8 + len(rtp), 0) + rtp
            total = 20 + len(udp)
            ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, total, i & 0xffff, 0, 64, 17, 0,
                             bytes((10, 0, 0, 1)), bytes((10, 0, 0, 2)))
            ip = ip[:10] + struct.pack("!H", ip_checksum(ip)) + ip[12:]
            eth = struct.pack("!6s6sH", b"\x00\x00\x00\x00\x00\x01",
                              b"\x00\x00\x00\x00\x00\x02", 0x0800)
            pkt = eth + ip + udp
            usec = i * PTIME_US
            f.write(struct.pack("<IIII", usec // 1000000, usec % 1000000, len(pkt), len(pkt)))
            f.write(pkt)
            seq += 1
            ts += PAYLOAD
    print("wrote", out, PACKETS, "packets")


if __name__ == "__main__":
    main()
