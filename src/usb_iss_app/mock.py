"""Mock USB-ISS (SPEC §3). Emulates only what the datasheet defines and we implement."""
from __future__ import annotations

import logging

from . import iss
from .transport import DEFAULT_TIMEOUT, Transport

log = logging.getLogger(__name__)


class MockTransport(Transport):
    def __init__(self, firmware: int = 0x09, mode: int = 0x40, serial: str = "00000001"):
        self.firmware = firmware
        self.mode = mode
        self.serial = serial
        self.unhandled: list[bytes] = []
        self._rx = bytearray()
        self._tx = bytearray()
        self.closed = False
        self._force_nack: int | None = None

    def force_next_mode_nack(self, reason: int) -> None:
        """Test-only: the next ISS_MODE frame is consumed and answered 00 <reason>."""
        self._force_nack = reason

    @staticmethod
    def _mode_frame_len(mode: int) -> int | None:
        """Total frame length by mode byte, datasheet pp.6-10; None for an unknown mode."""
        if mode in (iss.IO_MODE, iss.IO_CHANGE) or mode in iss.I2C_MODES:
            return 4
        if iss.SPI_MODE <= mode <= iss.SPI_MODE | 3:
            return 4
        if mode & ~iss.SERIAL in iss.I2C_MODES and mode & iss.SERIAL:
            return 5
        if mode == iss.IO_MODE | iss.SERIAL:
            return 6
        return None

    def _mode_command(self) -> bool:
        """Handle a 5A 02 frame at the head of _tx. False if it is still incomplete."""
        if len(self._tx) < 3:
            return False
        mode = self._tx[2]
        n = self._mode_frame_len(mode)
        if n is None:
            # ASSUMPTION (not verified on hardware): an unknown mode byte is NACKed 00 05
            # after only "5A 02 <mode>" has been consumed.
            self._rx += bytes([0x00, 0x05])
            del self._tx[:3]
            return True
        if len(self._tx) < n:
            return False  # wait for the whole frame; its bytes are never commands
        if self._force_nack is not None:
            self._rx += bytes([0x00, self._force_nack])
            self._force_nack = None
        else:
            self._rx += bytes([0xFF, 0x00])
            # ASSUMPTION (see NEXT 01 req. 9): IO_CHANGE leaves the reported mode unchanged.
            if mode != iss.IO_CHANGE:
                self.mode = mode
        del self._tx[:n]
        return True

    def write(self, data: bytes) -> None:
        self._tx += data
        self._process()

    def _process(self) -> None:
        while self._tx:
            if self._tx[0] != 0x5A or len(self._tx) < 2:
                if self._tx[0] == 0x5A:
                    return  # wait for the sub-command byte
                self._drop(1)
                continue
            sub = self._tx[1]
            if sub == 0x01:  # ISS_VERSION, datasheet p.5
                self._rx += bytes([0x07, self.firmware, self.mode])
            elif sub == 0x02:  # ISS_MODE, datasheet p.6
                if not self._mode_command():
                    return
                continue
            elif sub == 0x03:  # GET_SER_NUM, datasheet p.5
                self._rx += self.serial.encode("ascii")
            else:
                self._drop(2)
                continue
            del self._tx[:2]

    def _drop(self, n: int) -> None:
        chunk = bytes(self._tx[:n])
        self.unhandled.append(chunk)
        log.warning("MockTransport: unhandled request %s", chunk.hex(" "))
        del self._tx[:n]

    def read(self, n: int, timeout: float = DEFAULT_TIMEOUT) -> bytes:
        out = bytes(self._rx[:n])
        del self._rx[:n]
        return out

    def close(self) -> None:
        self.closed = True
