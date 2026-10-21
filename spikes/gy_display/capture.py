"""Spike step 1: set IO_MODE+SERIAL 115200, receive-poll for 30 s, parse GY-MCU90640 frames. No GUI.

Sends no bytes to the GY: every SERIAL_IO is the bare receive poll (datasheet p.19).
Run from the repo root:  .venv/bin/python spikes/gy_display/capture.py [seconds]
"""
from __future__ import annotations

import sys
import time
from collections import Counter

from usb_iss_app import iss
from usb_iss_app.transport import SerialTransport

from gyframe import FrameParser, SpikeLog

BAUD = 115200
IO_TYPE = 0xAA  # all pairs digital input (HARDWARE.md); I/O1/I/O2 are RX/TX in serial mode (p.8)


def main() -> int:
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    log = SpikeLog("capture")
    log(f"log {log.path.name}; duration {duration:.0f} s")
    t = SerialTransport()
    raw_f = log.open_raw()
    try:
        v = iss.version(t)
        log(f"version: module_id {v.module_id} firmware 0x{v.firmware:02X} mode 0x{v.mode:02X} ({iss.decode_mode(v.mode)})")
        log(f"serial number {iss.serial_number(t)}")

        frame = iss.build_io_serial(BAUD, IO_TYPE)
        log(f"set_mode {frame.hex(' ').upper()}")
        iss.set_mode(t, frame)
        v = iss.version(t)
        log(f"mode byte read back 0x{v.mode:02X} ({iss.decode_mode(v.mode)})")
        if v.mode != iss.IO_MODE | iss.SERIAL:
            log("STOP: mode byte is not 0x01")
            return 1

        parser = FrameParser()
        rx_hist: Counter[int] = Counter()
        polls = total = full = nacks = 0
        first: bytes | None = None
        last = None
        good_times: list[float] = []
        t0 = time.monotonic()
        end = t0 + duration
        try:
            while (now := time.monotonic()) < end:
                r = iss.serial_io(t)
                polls += 1
                n = len(r.rx)
                rx_hist[n] += 1
                if not r.ack:
                    nacks += 1
                if n:
                    total += n
                    if n == iss.SERIAL_RX_MAX:
                        full += 1
                    if first is None:
                        first = r.rx
                    raw_f.write(r.rx)
                    for f in parser.feed(r.rx):
                        last = f
                        good_times.append(f.t)
        except KeyboardInterrupt:
            log("interrupted")
        elapsed = time.monotonic() - t0

        checked = parser.good + parser.bad_checksum
        log(f"elapsed {elapsed:.2f} s")
        log(f"polls {polls} ({polls / elapsed:.1f}/s); NACKs {nacks}")
        log(f"total bytes {total} ({total / elapsed:.0f} B/s; 115200 8N1 line max ~11520 B/s)")
        log(f"polls returning the full {iss.SERIAL_RX_MAX} bytes (possible overflow): {full}")
        log("rx count histogram: " + " ".join(f"{k}:{rx_hist[k]}" for k in sorted(rx_hist)))
        if first is not None:
            log(f"first rx bytes: {first[:32].hex(' ').upper()}")
        log(f"frames found {checked}; checksum pass {parser.good}, fail {parser.bad_checksum}"
            + (f" ({parser.bad_checksum / checked * 100:.1f}% fail)" if checked else ""))
        log(f"bytes discarded while resyncing {parser.discarded}")
        log(f"good-frame rate {parser.good / elapsed:.2f} /s over the run")
        if len(good_times) >= 2:
            span = good_times[-1] - good_times[0]
            log(f"good-frame rate {(len(good_times) - 1) / span:.2f} /s between first and last good frame")
        if last is not None:
            log(f"last good frame: min {last.min:.2f} C, max {last.max:.2f} C, Ta {last.ta:.2f} C")
        else:
            log("no good frame")
        log(f"raw stream saved to {log.path.with_suffix('.bin').name}")
        return 0
    finally:
        raw_f.close()
        t.close()
        log("port closed")
        log.close()


if __name__ == "__main__":
    sys.exit(main())
