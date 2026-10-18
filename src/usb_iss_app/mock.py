"""Mock USB-ISS (SPEC §3). Emulates only what the datasheet defines and we implement."""
from __future__ import annotations

import logging

from . import iss
from .transport import DEFAULT_TIMEOUT, Transport

log = logging.getLogger(__name__)


# Hardware: a 60-byte I2C_DIRECT frame (0x57 plus 59 STOPs) answered FF 00, so the device accepts at least
# 60 bytes (docs/iterations/04/logs/build-hw-20261018-021131.txt). The builder limit stays at 59 (D-007).
# ASSUMPTION: longer frames overflow, as p.15 says; 61 bytes has not been tried.
MOCK_DIRECT_OVERFLOW = 60


class MockI2cDevice:
    """A test-defined I2C slave: memory plus a pointer that post-increments and wraps at size.

    addr_bytes (0, 1 or 2) is the number of internal address bytes that I2C_DIRECT writes send
    before data (pp.15-16). Only I2C_DIRECT uses it; the register commands set the pointer themselves.
    """

    def __init__(self, size: int = 256, addr_bytes: int = 1):
        if addr_bytes not in (0, 1, 2):
            raise ValueError(f"addr_bytes {addr_bytes} is not 0, 1 or 2")
        self.size = size
        self.addr_bytes = addr_bytes
        self.mem = bytearray(size)
        self.pointer = 0
        self._addr_buf = bytearray()

    def begin_direct_write(self) -> None:
        """A write transaction starts (I2C_DIRECT): the next addr_bytes bytes set the pointer."""
        self._addr_buf.clear()

    def direct_write(self, data: bytes) -> None:
        """I2C_DIRECT write bytes: pointer bytes first, high byte first, then data at the pointer."""
        for b in data:
            if len(self._addr_buf) < self.addr_bytes:
                self._addr_buf.append(b)
                if len(self._addr_buf) == self.addr_bytes:
                    self.pointer = int.from_bytes(self._addr_buf, "big") % self.size
            else:
                self.write(bytes([b]))

    def write(self, data: bytes) -> None:
        for b in data:
            self.mem[self.pointer] = b
            self.pointer = (self.pointer + 1) % self.size

    def read(self, n: int) -> bytes:
        out = bytearray()
        for _ in range(n):
            out.append(self.mem[self.pointer])
            self.pointer = (self.pointer + 1) % self.size
        return bytes(out)


class MockSpiDevice:
    """A test-defined SPI slave (p.17). Subclasses override transfer()."""

    def transfer(self, data: bytes) -> bytes:
        """One CE-low period: byte i of the result is what the device shifts out while it receives byte i."""
        return b"\xff" * len(data)


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
        self.i2c_devices: dict[int, MockI2cDevice] = {}  # keyed by even 8-bit address; empty like the bench bus
        self.spi_device: MockSpiDevice | None = None

    def _is_i2c_mode(self) -> bool:
        return self.mode in iss.I2C_MODES or bool(self.mode & iss.SERIAL and self.mode & ~iss.SERIAL in iss.I2C_MODES)

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
        # Observed on hardware once (IO_MODE, all pins digital input, 63 0F -> 00); the other cases are an assumption.
        outputs = [p for p in self._general_pins()
                   if self._pin_type(p) in (iss.IoType.OUTPUT_LOW, iss.IoType.OUTPUT_HIGH)]
        for pin in outputs:
            self._out = self._out & ~(1 << pin) | (ss & (1 << pin))
        self._rx.append(0xFF if outputs else 0x00)

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
        """GETAD, p.20, following the device (SPEC §8 erratum)."""
        # p.20 says 0000 for a digital input; device fw 0x09 converts anyway (SPEC §8).
        if (1 <= ch <= 4 and ch - 1 in self._general_pins()
                and self._pin_type(ch - 1) in (iss.IoType.DIGITAL_INPUT, iss.IoType.ANALOGUE_INPUT)):
            return bytes([self.adc[ch - 1] >> 8, self.adc[ch - 1] & 0xFF])
        # Output pins and I2C/serial pins: datasheet; untested on hardware. Channels outside 1-4: confirmed on hardware.
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

    @staticmethod
    def _i2c_frame_len(tx: bytearray) -> int | None:
        """Total length of the I2C frame at the head of tx, pp.11-16; None if not yet known."""
        cmd = tx[0]
        if cmd == iss.I2C_TEST:
            return 2
        if len(tx) < 2:
            return None
        read = bool(tx[1] & 1)
        if cmd == iss.I2C_SGL:
            return 2 if read else 3
        if cmd == iss.I2C_AD0:
            return 3 if read else (3 + tx[2] if len(tx) >= 3 else None)
        if cmd == iss.I2C_AD1:
            return 4 if read else (4 + tx[3] if len(tx) >= 4 else None)
        # I2C_AD2
        return 5 if read else (5 + tx[4] if len(tx) >= 5 else None)

    def _i2c_command(self) -> bool:
        """I2C_SGL/AD0/AD1/AD2/TEST, pp.11-16. False if the frame is still incomplete."""
        n = self._i2c_frame_len(self._tx)
        if n is None or len(self._tx) < n:
            return False  # wait for the whole frame; its bytes are never commands
        frame = bytes(self._tx[:n])
        del self._tx[:n]
        if not self._is_i2c_mode():
            if frame[0] == iss.I2C_TEST and self.mode == iss.IO_MODE:
                # Hardware: in IO_MODE the device answers I2C_TEST with 00 (docs/iterations/03/logs/
                # build-hw-20261017-233218.txt, review-hw-20261018-001847.txt).
                self._rx.append(0x00)
                return True
            # ASSUMPTION: outside the I2C modes the other frames (and I2C_TEST in IO_MODE+SERIAL and
            # SPI) are consumed and dropped with no reply.
            self.unhandled.append(frame)
            log.warning("MockTransport: I2C command outside I2C mode dropped")
            return True
        cmd = frame[0]
        read = bool(frame[1] & 1)
        dev = self.i2c_devices.get(frame[1] & 0xFE)
        if cmd == iss.I2C_TEST:
            # ASSUMPTION: FF for "non-zero" (p.16).
            self._rx.append(0xFF if dev else 0x00)
            return True
        if cmd == iss.I2C_SGL:
            count, data = 1, frame[2:]
        elif cmd == iss.I2C_AD0:
            count, data = frame[2], frame[3:]
        elif cmd == iss.I2C_AD1:
            count, data = frame[3], frame[4:]
            if dev:
                dev.pointer = frame[2] % dev.size
        else:
            count, data = frame[4], frame[5:]
            if dev:
                dev.pointer = (frame[2] << 8 | frame[3]) % dev.size
        if read:
            # ASSUMPTION: an absent device reads as FF, the 4.7k pull-ups (p.3) holding SDA high.
            self._rx += dev.read(count) if dev else b"\xff" * count
        elif dev:
            dev.write(data)
            self._rx.append(0xFF)  # ASSUMPTION: the datasheet only says "non-zero"
        else:
            self._rx.append(0x00)
        return True

    def _direct_command(self) -> None:
        """I2C_DIRECT, pp.15-16; D-007. The whole of _tx is the frame."""
        # ASSUMPTION (D-007): no length byte, so the frame runs from 57 to the end of the write() call.
        frame = bytes(self._tx)
        self._tx.clear()
        if not self._is_i2c_mode():
            if self.mode == iss.IO_MODE:
                # Hardware: in IO_MODE the device answers 57 01 30 A0 03 with a single 00
                # (docs/iterations/04/logs/build-hw-20261018-021131.txt).
                self._rx.append(0x00)
                return
            # ASSUMPTION: in IO_MODE+SERIAL and SPI the frame is consumed and dropped with no reply.
            self.unhandled.append(frame)
            log.warning("MockTransport: I2C_DIRECT outside I2C mode dropped")
            return
        if len(frame) > MOCK_DIRECT_OVERFLOW:
            self._rx += bytes([0x00, 0x02])  # Buffer Overflow, p.15; nothing is executed
            return
        out = bytearray()
        want_addr = False
        wr_dev: MockI2cDevice | None = None  # device addressed for writing
        rd_dev: MockI2cDevice | None = None  # device addressed for reading
        i = 1
        while i < len(frame):
            sub = frame[i]
            i += 1
            if sub in (iss.I2C_DIRECT_START, iss.I2C_DIRECT_RESTART):
                want_addr, wr_dev, rd_dev = True, None, None
            elif sub == iss.I2C_DIRECT_STOP:
                want_addr, wr_dev, rd_dev = False, None, None
            elif sub == iss.I2C_DIRECT_NACK:
                pass  # no effect in the mock
            elif 0x20 <= sub <= 0x2F:
                k = sub - iss.I2C_DIRECT_READ_BASE + 1
                # ASSUMPTION: with no device addressed for reading, the pull-ups (p.3) give FF.
                out += rd_dev.read(k) if rd_dev else b"\xff" * k
            elif 0x30 <= sub <= 0x3F:
                k = sub - iss.I2C_DIRECT_WRITE_BASE + 1
                if len(frame) - i < k:
                    self._rx += bytes([0x00, 0x03])  # Buffer Underflow, p.15
                    return
                data = frame[i:i + k]
                i += k
                if want_addr:
                    want_addr = False
                    addr, data = data[0], data[1:]
                    dev = self.i2c_devices.get(addr & 0xFE)
                    if dev is None:
                        # ASSUMPTION: the device stops at the first unacknowledged address.
                        self._rx += bytes([0x00, 0x01])  # Device Error, p.15
                        return
                    if addr & 1:  # the low bit selects read
                        rd_dev = dev
                    else:
                        wr_dev = dev
                        dev.begin_direct_write()
                if wr_dev:
                    wr_dev.direct_write(data)
            # Any other byte: hardware ignores 0x05 and answers FF 00 (build-hw-20261018-021131.txt),
            # not 00 04 as p.15 suggests. ASSUMPTION: the same for every other unknown sub-command.
        self._rx += bytes([0xFF, len(out)]) + out

    def _spi_command(self) -> None:
        """SPI, p.17; D-007. The whole of _tx is the frame."""
        # ASSUMPTION (D-007): no length byte, so the frame runs from 61 to the end of the write() call.
        frame = bytes(self._tx)
        self._tx.clear()
        if not iss.SPI_MODE <= self.mode <= iss.SPI_MODE | 3:
            # Iterations 03 and 04 found IO_MODE answering I2C_TEST and I2C_DIRECT with a single 00; SPI has not
            # been tried. ASSUMPTION: outside the SPI modes the frame is consumed and dropped with no reply.
            self.unhandled.append(frame)
            log.warning("MockTransport: SPI outside SPI mode dropped")
            return
        data = frame[1:]
        if len(frame) > iss.SPI_FRAME_MAX:
            # ASSUMPTION: the datasheet doesn't say what the device does with an over-long frame.
            self._rx.append(0x00)
            return
        if not data:
            self._rx.append(0xFF)  # ASSUMPTION: one byte sent, one byte back (p.17)
            return
        # ASSUMPTION: one frame is one CE-low period, so one transfer() call (needed by the p.17 23K256 examples).
        # ASSUMPTION: with nothing attached SDI floats and reads FF, as for the empty I2C bus.
        out = self.spi_device.transfer(data) if self.spi_device else b"\xff" * len(data)
        self._rx += b"\xff" + out

    def write(self, data: bytes) -> None:
        self._tx += data
        self._process()

    def _process(self) -> None:
        while self._tx:
            head = self._tx[0]
            if head == iss.SERIAL_IO:
                self._serial_command()
                return
            if head == iss.I2C_DIRECT:
                self._direct_command()
                return
            if head == iss.SPI_IO:
                self._spi_command()
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
            if head in (iss.I2C_SGL, iss.I2C_AD0, iss.I2C_AD1, iss.I2C_AD2, iss.I2C_TEST):
                if not self._i2c_command():
                    return
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
