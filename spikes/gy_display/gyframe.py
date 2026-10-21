"""GY-MCU90640 serial frame parser and spike log helper. Not part of usb_iss_app.

Frame format, GY manual §IV.2-3 and SPIKE-gy-display.md step 1:
  bytes 0-1     5A 5A header
  bytes 2-3     02 06 (count 0x0602 = 1538, little-endian)
  bytes 4-1539  768 signed LE int16 pixels, x100 degC
  bytes 1540-1541 Ta, signed LE int16, x100 degC
  bytes 1542-1543 checksum: sum of the 771 LE words in bytes 0-1541, mod 65536
"""
from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from pathlib import Path

HEADER = b"\x5a\x5a\x02\x06"
FRAME_LEN = 1544
PIXELS = 768
COLS, ROWS = 32, 24


@dataclass(frozen=True)
class Frame:
    pixels: tuple[float, ...]  # degC, in stream order: pixel i is row i // 32, column i % 32 + 1
    ta: float  # degC
    t: float  # time.monotonic() when the frame completed

    @property
    def min(self) -> float:
        return min(self.pixels)

    @property
    def max(self) -> float:
        return max(self.pixels)


def checksum_ok(raw: bytes) -> bool:
    words = struct.unpack_from("<771H", raw, 0)
    (want,) = struct.unpack_from("<H", raw, 1542)
    return sum(words) & 0xFFFF == want


def decode(raw: bytes, t: float) -> Frame:
    vals = struct.unpack_from("<769h", raw, 4)
    return Frame(tuple(v / 100 for v in vals[:PIXELS]), vals[PIXELS] / 100, t)


class FrameParser:
    """Feed arbitrary byte chunks; returns checksum-valid frames. Counts everything else."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.good = 0
        self.bad_checksum = 0
        self.discarded = 0  # bytes dropped while hunting for a header

    def feed(self, data: bytes, t: float | None = None) -> list[Frame]:
        if t is None:
            t = time.monotonic()
        self._buf += data
        out: list[Frame] = []
        while True:
            i = self._buf.find(HEADER)
            if i < 0:
                # keep up to 3 trailing bytes: they may be the start of a header
                keep = 3
                drop = max(0, len(self._buf) - keep)
                self.discarded += drop
                del self._buf[:drop]
                return out
            if i:
                self.discarded += i
                del self._buf[:i]
            if len(self._buf) < FRAME_LEN:
                return out
            raw = bytes(self._buf[:FRAME_LEN])
            if checksum_ok(raw):
                self.good += 1
                out.append(decode(raw, t))
                del self._buf[:FRAME_LEN]
            else:
                # resync: skip this header and look for the next one
                self.bad_checksum += 1
                self.discarded += 2
                del self._buf[:2]


class SpikeLog:
    """Timestamped log file written by the script itself. Never overwrites (mode 'x')."""

    def __init__(self, name: str) -> None:
        logs = Path(__file__).resolve().parent / "logs"
        logs.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = logs / f"{name}-{stamp}.log"
        self._f = self.path.open("x", encoding="utf-8")

    def open_raw(self):
        """Raw received bytes, next to the log, same stamp. Also never overwrites."""
        return self.path.with_suffix(".bin").open("xb")

    def __call__(self, msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        self._f.write(line + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()
