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
        # ASSUMPTION: power-up IO_TYPE is all digital input. Changelog v7 (p.2) says only
        # I/O1 and I/O2 power up as inputs; I/O3 and I/O4 are assumed the same.
        self.io_type = 0xAA
        self.inputs = 0  # test-settable: 4-bit levels seen on digital-input pins
        self.adc = [0, 0, 0, 0]  # test-settable: raw 0-1023 per channel
        self._out = 0  # output levels, bit n = I/O(n+1)
        self._apply_io_type(self.io_type)
        self._force_setpins_nack = False
        self.serial_sent = bytearray()
        self.hold_serial_tx = False  # test-only: keep accepted bytes pending
        self._tx_pending = bytearray()
        self._serial_rx = bytearray()

    def force_next_setpins_nack(self) -> None:
        """Test-only: the next SETPINS is consumed and answered 00."""
        self._force_setpins_nack = True

    def inject_serial_rx(self, data: bytes) -> None:
        """Test-only: bytes arriving on the serial RX line."""
        room = iss.SERIAL_RX_MAX - len(self._serial_rx)
        # ASSUMPTION: the datasheet does not say what happens on receive overflow; extra bytes are dropped.
        if len(data) > room:
            log.warning("MockTransport: serial rx overflow, dropped %s", bytes(data[room:]).hex(" "))
        self._serial_rx += data[:max(room, 0)]

    def _is_serial_mode(self) -> bool:
        m = self.mode
        return m == iss.IO_MODE | iss.SERIAL or (bool(m & iss.SERIAL) and m & ~iss.SERIAL in iss.I2C_MODES)

    def _general_pins(self) -> tuple[int, ...]:
        """Pins usable as general I/O in the current mode, datasheet p.3 pin table (0-based)."""
        m = self.mode
        if m == iss.IO_MODE:
            return (0, 1, 2, 3)
        if m == iss.IO_MODE | iss.SERIAL:
            return (2, 3)
        if m in iss.I2C_MODES:
            return (0, 1)
        return ()  # I2C+SERIAL, SPI

    def _pin_type(self, pin: int) -> int:
        return self.io_type >> (2 * pin) & 3

    def _apply_io_type(self, tt: int) -> None:
        self.io_type = tt
        self._out = 0
        for pin in self._general_pins():
            if self._pin_type(pin) == iss.IoType.OUTPUT_HIGH:
                self._out |= 1 << pin

    def _serial_command(self) -> None:
        """SERIAL_IO, p.19. The whole of _tx is the frame."""
        # ASSUMPTION: no length byte, so the frame runs from 62 to the end of the write() call.
        payload = bytes(self._tx[1:])
        self._tx.clear()
        if not self._is_serial_mode():
            # ASSUMPTION: outside the serial modes the datasheet defines nothing; drop, no reply.
            self.unhandled.append(bytes([iss.SERIAL_IO]) + payload)
            log.warning("MockTransport: SERIAL_IO outside serial mode dropped")
            return
        if not self.hold_serial_tx:
            self.serial_sent += self._tx_pending
            self._tx_pending.clear()
        ack = len(payload) <= iss.SERIAL_TX_MAX - len(self._tx_pending)
        if ack:
            self._tx_pending += payload
            if not self.hold_serial_tx:
                self.serial_sent += self._tx_pending
                self._tx_pending.clear()
        rx = bytes(self._serial_rx)
        self._serial_rx.clear()
        self._rx += bytes([0xFF if ack else 0x00, len(self._tx_pending), len(rx)]) + rx

    def _setpins(self, ss: int) -> None:
        """SETPINS, p.20: changes output pins only."""
        if self._force_setpins_nack:
            self._force_setpins_nack = False
            self._rx.append(0x00)
            return
        for pin in self._general_pins():
            if self._pin_type(pin) in (iss.IoType.OUTPUT_LOW, iss.IoType.OUTPUT_HIGH):
                self._out = self._out & ~(1 << pin) | (ss & (1 << pin))
        self._rx.append(0xFF)

    def _getpins(self) -> int:
        # ASSUMPTION: bits for pins that are not general I/O, or are analogue inputs, read 0.
        v = 0
        for pin in self._general_pins():
            t = self._pin_type(pin)
            if t in (iss.IoType.OUTPUT_LOW, iss.IoType.OUTPUT_HIGH):
                v |= self._out & (1 << pin)
            elif t == iss.IoType.DIGITAL_INPUT:
                v |= self.inputs & (1 << pin)
        return v

    def _getad(self, ch: int) -> bytes:
        """GETAD, p.20: 00 00 unless the channel is a general-I/O analogue input."""
        if 1 <= ch <= 4 and ch - 1 in self._general_pins() and self._pin_type(ch - 1) == iss.IoType.ANALOGUE_INPUT:
            return bytes([self.adc[ch - 1] >> 8, self.adc[ch - 1] & 0xFF])
        return b"\x00\x00"

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
            # Hardware (docs/iterations/01/logs/build-hw-20261017-003245.txt): from I2C_S_100KHZ,
            # IO_CHANGE returned FF 00 and the mode stayed 0x40. ASSUMPTION: the same from other starting modes.
            if mode != iss.IO_CHANGE:
                self.mode = mode
            # IO_TYPE is carried by IO_MODE, IO_CHANGE, I2C_MODE (byte 3) and IO_MODE+SERIAL (byte 5);
            # I2C+SERIAL and SPI frames carry none.
            if mode == iss.IO_MODE | iss.SERIAL:
                self._apply_io_type(self._tx[5])
            elif mode in (iss.IO_MODE, iss.IO_CHANGE) or mode in iss.I2C_MODES:
                self._apply_io_type(self._tx[3])
        del self._tx[:n]
        return True

    def write(self, data: bytes) -> None:
        self._tx += data
        self._process()

    def _process(self) -> None:
        while self._tx:
            head = self._tx[0]
            if head == iss.SERIAL_IO:
                self._serial_command()
                return
            if head == iss.GETPINS:
                self._rx.append(self._getpins())
                del self._tx[:1]
                continue
            if head in (iss.SETPINS, iss.GETAD):
                if len(self._tx) < 2:
                    return
                if head == iss.SETPINS:
                    self._setpins(self._tx[1])
                else:
                    self._rx += self._getad(self._tx[1])
                del self._tx[:2]
                continue
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
