"""Offline checks for the spike parser. Run: .venv/bin/python -m pytest spikes/gy_display -q"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gyframe import FRAME_LEN, FrameParser, checksum_ok  # noqa: E402


def make_frame(pixels, ta):
    body = b"\x5a\x5a\x02\x06" + struct.pack("<768h", *pixels) + struct.pack("<h", ta)
    s = sum(struct.unpack("<771H", body)) & 0xFFFF
    return body + struct.pack("<H", s)


def test_manual_example_words_and_signed_pixels():
    f = make_frame([0x0E6E] + [-500] * 766 + [0x0E05], 0x0E8D)
    assert len(f) == FRAME_LEN and checksum_ok(f)
    (got,) = FrameParser().feed(f)
    assert got.pixels[0] == 36.94 and got.pixels[1] == -5.0 and got.pixels[767] == 35.89
    assert got.ta == 37.25


def test_resync_across_chunks_garbage_and_bad_checksum():
    good = make_frame(list(range(768)), 2500)
    bad = bytearray(good)
    bad[100] ^= 0xFF
    stream = b"\x01\x5a\x5a\x00" + bytes(bad) + b"\x5a" + good + good[:700]
    p = FrameParser()
    out = []
    for i in range(0, len(stream), 62):  # 62-byte chunks, like SERIAL_IO
        out += p.feed(stream[i:i + 62])
    out += p.feed(good[700:])
    assert len(out) == 2 and p.good == 2 and p.bad_checksum == 1
