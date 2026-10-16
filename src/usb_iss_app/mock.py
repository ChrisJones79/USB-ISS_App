"""Mock USB-ISS (SPEC §3). Emulates only what the datasheet defines and we implement."""
from __future__ import annotations

import logging

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
