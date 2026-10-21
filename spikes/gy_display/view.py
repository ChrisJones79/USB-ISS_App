"""Spike step 2: live GY-MCU90640 heatmap over USB-ISS IO_MODE+SERIAL (PySide6).

Polling runs in a worker thread; the GUI gets only checksum-valid frames.
Sends no bytes to the GY: every SERIAL_IO is the bare receive poll (datasheet p.19).

Run from the repo root:
  .venv/bin/python spikes/gy_display/view.py                 # live, port from USB_ISS_PORT
  .venv/bin/python spikes/gy_display/view.py --replay X.bin  # replay a capture, no hardware
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (QApplication, QCheckBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel,
                               QVBoxLayout, QWidget)

from gyframe import COLS, ROWS, Frame, FrameParser, SpikeLog

BAUD = 115200
IO_TYPE = 0xAA  # all pairs digital input (HARDWARE.md)
CELL = 20  # px per sensor cell
STATS_EVERY = 0.5  # s between stats signals
LOG_EVERY = 5.0  # s between stats lines in the log


class PollWorker(QThread):
    """Owns the port for its whole life: opens, sets mode, polls, closes."""

    frame = Signal(object)  # Frame
    stats = Signal(dict)
    failed = Signal(str)

    def __init__(self, log: SpikeLog, replay: Path | None = None) -> None:
        super().__init__()
        self._log = log
        self._replay = replay

    def run(self) -> None:
        try:
            if self._replay:
                self._run_replay()
            else:
                self._run_live()
        except Exception as e:  # report to the GUI and the log, never die silently
            self._log(f"worker error: {type(e).__name__}: {e}")
            self.failed.emit(f"{type(e).__name__}: {e}")

    def _run_live(self) -> None:
        from usb_iss_app import iss
        from usb_iss_app.transport import SerialTransport

        t = SerialTransport()
        try:
            v = iss.version(t)
            self._log(f"version: module_id {v.module_id} firmware 0x{v.firmware:02X} mode 0x{v.mode:02X} ({iss.decode_mode(v.mode)})")
            mode = iss.build_io_serial(BAUD, IO_TYPE)
            self._log(f"set_mode {mode.hex(' ').upper()}")
            iss.set_mode(t, mode)
            v = iss.version(t)
            self._log(f"mode byte read back 0x{v.mode:02X} ({iss.decode_mode(v.mode)})")
            if v.mode != iss.IO_MODE | iss.SERIAL:
                raise RuntimeError(f"mode byte 0x{v.mode:02X} is not 0x01")
            self._loop(lambda: iss.serial_io(t).rx, full=iss.SERIAL_RX_MAX)
        finally:
            t.close()
            self._log("port closed")

    def _run_replay(self) -> None:
        data = self._replay.read_bytes()
        self._log(f"replay {self._replay} ({len(data)} bytes) at ~6000 B/s")
        pos = 0
        rate = 6000.0
        t0 = time.monotonic()

        def chunk() -> bytes:
            nonlocal pos
            want = int((time.monotonic() - t0) * rate) % len(data) if data else 0
            if want < pos:  # wrapped: loop the file
                out, pos = data[pos:] + data[:want], want
            else:
                out, pos = data[pos:want], want
            time.sleep(0.002)
            return out

        self._loop(chunk, full=None)

    def _loop(self, poll, full: int | None) -> None:
        parser = FrameParser()
        polls = total = fulls = shown = 0
        t0 = last_stats = last_log = time.monotonic()
        recent: list[float] = []
        latest: Frame | None = None

        def snapshot(now: float) -> dict:
            while recent and now - recent[0] > 2.0:
                recent.pop(0)
            el = now - t0
            return {
                "elapsed": el, "polls_s": polls / el if el else 0.0, "bytes": total, "full": fulls,
                "good": parser.good, "bad": parser.bad_checksum, "discarded": parser.discarded,
                "fps": len(recent) / 2.0, "shown": shown,
            }

        while not self.isInterruptionRequested():
            rx = poll()
            polls += 1
            if rx:
                total += len(rx)
                if full is not None and len(rx) == full:
                    fulls += 1
                for f in parser.feed(rx):
                    recent.append(f.t)
                    latest = f
                if latest is not None:
                    self.frame.emit(latest)  # only the newest frame; the GUI never queues a backlog
                    shown += 1
                    latest = None
            now = time.monotonic()
            if now - last_stats >= STATS_EVERY:
                last_stats = now
                self.stats.emit(snapshot(now))
            if now - last_log >= LOG_EVERY:
                last_log = now
                self._log_stats(snapshot(now))
        self._log("stop requested")
        self._log_stats(snapshot(time.monotonic()))

    def _log_stats(self, s: dict) -> None:
        self._log(f"t {s['elapsed']:.1f} s: polls/s {s['polls_s']:.0f}, bytes {s['bytes']}, full polls {s['full']}, "
                  f"good {s['good']}, checksum fail {s['bad']}, discarded {s['discarded']}, fps {s['fps']:.2f}, "
                  f"frames shown {s['shown']}")


# Colour map: black - blue - magenta - orange - yellow - white, auto-ranged per frame.
_STOPS = [(0.0, (0, 0, 0)), (0.2, (30, 0, 120)), (0.45, (170, 0, 150)), (0.7, (240, 90, 0)),
          (0.9, (255, 220, 0)), (1.0, (255, 255, 255))]


def colour(x: float) -> QColor:
    x = min(1.0, max(0.0, x))
    for (a, ca), (b, cb) in zip(_STOPS, _STOPS[1:]):
        if x <= b:
            u = (x - a) / (b - a)
            return QColor(*(round(p + (q - p) * u) for p, q in zip(ca, cb)))
    return QColor(*_STOPS[-1][1])


class Heatmap(QWidget):
    """32x24 cells. Pixel i is row i // 32, column i % 32 + 1; column 1 is drawn on the right (GY manual p.3).

    Colour scale: auto (each frame's own min..max) unless a fixed (lo, hi) range is set.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(COLS * CELL, ROWS * CELL)
        self._img: QImage | None = None
        self.fixed: tuple[float, float] | None = None

    def scale(self, f: Frame) -> tuple[float, float]:
        return self.fixed if self.fixed else (f.min, f.max)

    def show_frame(self, f: Frame) -> None:
        lo, hi = self.scale(f)
        span = (hi - lo) or 1.0
        img = QImage(COLS, ROWS, QImage.Format.Format_RGB32)
        for i, temp in enumerate(f.pixels):
            row, col = divmod(i, COLS)  # col 0 here is the manual's column 1
            img.setPixelColor(COLS - 1 - col, row, colour((temp - lo) / span))
        self._img = img
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        if self._img is None:
            p.fillRect(self.rect(), Qt.GlobalColor.darkGray)
            p.setPen(Qt.GlobalColor.white)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "waiting for a frame")
        else:
            p.drawImage(self.rect(), self._img)  # nearest-neighbour scaling: one block per cell


class Window(QWidget):
    def __init__(self, worker: PollWorker, log: SpikeLog, fixed: tuple[float, float] | None = None) -> None:
        super().__init__()
        self._worker, self._log = worker, log
        self.setWindowTitle("GY-MCU90640 via USB-ISS (spike)")
        self.heat = Heatmap()
        self.labels = {k: QLabel("-") for k in ("min", "max", "Ta", "scale", "frames/s", "checksum fail", "good", "polls/s")}
        grid = QGridLayout()
        for n, (k, lab) in enumerate(self.labels.items()):
            grid.addWidget(QLabel(k + ":"), n // 4, (n % 4) * 2)
            grid.addWidget(lab, n // 4, (n % 4) * 2 + 1)

        # Colour scale: auto by default; fixed lo..hi when ticked.
        self.fixed_box = QCheckBox("fixed range")
        self.lo_spin, self.hi_spin = QDoubleSpinBox(), QDoubleSpinBox()
        for s, v in ((self.lo_spin, 15.0), (self.hi_spin, 35.0)):
            s.setRange(-40.0, 300.0)  # GY manual: measuring range
            s.setDecimals(1)
            s.setSuffix(" °C")
            s.setValue(v)
        if fixed:
            self.lo_spin.setValue(fixed[0])
            self.hi_spin.setValue(fixed[1])
            self.fixed_box.setChecked(True)
        scale_row = QHBoxLayout()
        scale_row.addWidget(self.fixed_box)
        scale_row.addWidget(QLabel("from"))
        scale_row.addWidget(self.lo_spin)
        scale_row.addWidget(QLabel("to"))
        scale_row.addWidget(self.hi_spin)
        scale_row.addStretch()
        for w in (self.fixed_box, self.lo_spin, self.hi_spin):
            (w.toggled if w is self.fixed_box else w.valueChanged).connect(self.on_scale_changed)

        self.status = QLabel("")
        lay = QVBoxLayout(self)
        lay.addWidget(self.heat)
        lay.addLayout(grid)
        lay.addLayout(scale_row)
        lay.addWidget(self.status)
        self.on_scale_changed()
        worker.frame.connect(self.on_frame)
        worker.stats.connect(self.on_stats)
        worker.failed.connect(self.on_failed)

    def on_scale_changed(self, *_args) -> None:
        lo, hi = self.lo_spin.value(), self.hi_spin.value()
        if self.fixed_box.isChecked() and hi <= lo:
            self.status.setText("fixed range ignored: 'to' must be above 'from'")
            self.heat.fixed = None
        else:
            self.status.setText("")
            self.heat.fixed = (lo, hi) if self.fixed_box.isChecked() else None
        self._log(f"colour scale {'fixed %.1f..%.1f C' % self.heat.fixed if self.heat.fixed else 'auto'}")

    def on_frame(self, f: Frame) -> None:
        self.heat.show_frame(f)
        lo, hi = self.heat.scale(f)
        self.labels["min"].setText(f"{f.min:.2f} °C")
        self.labels["max"].setText(f"{f.max:.2f} °C")
        self.labels["Ta"].setText(f"{f.ta:.2f} °C")
        self.labels["scale"].setText(f"{'fixed' if self.heat.fixed else 'auto'} {lo:.1f}..{hi:.1f} °C")

    def on_stats(self, s: dict) -> None:
        self.labels["frames/s"].setText(f"{s['fps']:.2f}")
        self.labels["checksum fail"].setText(str(s["bad"]))
        self.labels["good"].setText(str(s["good"]))
        self.labels["polls/s"].setText(f"{s['polls_s']:.0f}")

    def on_failed(self, msg: str) -> None:
        self.status.setText("worker stopped: " + msg)

    def closeEvent(self, event) -> None:
        self._log("window closed")
        self._worker.requestInterruption()
        if not self._worker.wait(3000):
            self._log("worker did not stop within 3 s")
        event.accept()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", type=Path, help="play a capture .bin instead of opening the port")
    ap.add_argument("--snapshot", type=Path, help="after --seconds, save the window to this PNG and close")
    ap.add_argument("--seconds", type=float, default=0, help="close automatically after this many seconds")
    ap.add_argument("--fixed", type=float, nargs=2, metavar=("LO", "HI"),
                    help="start with a fixed colour range in degC (default: auto range per frame)")
    args = ap.parse_args()
    if args.fixed and args.fixed[1] <= args.fixed[0]:
        ap.error("--fixed: HI must be above LO")

    app = QApplication(sys.argv)
    log = SpikeLog("view-replay" if args.replay else "view")
    log(f"log {log.path.name}; {'replay ' + str(args.replay) if args.replay else 'live'}")
    worker = PollWorker(log, args.replay)
    win = Window(worker, log, tuple(args.fixed) if args.fixed else None)
    win.show()
    worker.start()
    if args.seconds:
        from PySide6.QtCore import QTimer

        def done() -> None:
            if args.snapshot:
                win.grab().save(str(args.snapshot))
                log(f"snapshot saved to {args.snapshot}")
            win.close()

        QTimer.singleShot(int(args.seconds * 1000), done)
    rc = app.exec()
    log(f"exit {rc}")
    log.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
