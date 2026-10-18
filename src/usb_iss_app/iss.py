"""Layer 2: USB-ISS protocol. Pure builders/parsers plus thin helpers."""
from __future__ import annotations

import enum
import math
from typing import NamedTuple

from .transport import Transport

ISS_CMD = 0x5A  # datasheet p.5
MODULE_ID = 7


class IssError(Exception):
    pass


class IssTimeout(IssError):
    """Fewer bytes than expected were received."""


class IssProtocolError(IssError):
    """Response bytes violate the datasheet."""


class IssNack(IssError):
    """A command answered NACK: ISS_MODE (00 rr, datasheet p.6), I2C_DIRECT (00 rr, p.15), or SETPINS (00, p.20) or an I2C write (00, pp.11-14); reason is None for the last two.

    The reason's name comes from I2C_DIRECT_NACK_REASONS when command is "I2C_DIRECT", otherwise from NACK_REASONS.
    """

    def __init__(self, reason: int | None = None, command: str = "ISS_MODE"):
        self.reason = reason
        if reason is None:
            self.name = None
            super().__init__(f"{command} NACK")
            return
        table = I2C_DIRECT_NACK_REASONS if command == "I2C_DIRECT" else NACK_REASONS
        self.name = table.get(reason, f"Unknown reason 0x{reason:02X}")
        super().__init__(f"{command} NACK: 0x{reason:02X} {self.name}")


class Version(NamedTuple):
    module_id: int
    firmware: int
    mode: int  # raw ISS_MODE byte; see decode_mode()


# ISS_VERSION (0x01), datasheet p.5: send 5A 01, receive module_id(7) firmware mode.
def build_version() -> bytes:
    return bytes([ISS_CMD, 0x01])


def parse_version(resp: bytes) -> Version:
    if len(resp) < 3:
        raise IssTimeout(f"ISS_VERSION: expected 3 bytes, got {len(resp)}")
    if resp[0] != MODULE_ID:
        raise IssProtocolError(f"ISS_VERSION: module_id {resp[0]} != {MODULE_ID}")
    return Version(resp[0], resp[1], resp[2])


# GET_SER_NUM (0x03), datasheet p.5: send 5A 03, receive 8 ASCII digits 0x30-0x39.
def build_serial_number() -> bytes:
    return bytes([ISS_CMD, 0x03])


def parse_serial_number(resp: bytes) -> str:
    if len(resp) < 8:
        raise IssTimeout(f"GET_SER_NUM: expected 8 bytes, got {len(resp)}")
    resp = resp[:8]
    if any(not 0x30 <= b <= 0x39 for b in resp):
        raise IssProtocolError(f"GET_SER_NUM: non-digit byte in {resp.hex(' ')}")
    return resp.decode("ascii")


def version(transport: Transport) -> Version:
    transport.write(build_version())
    return parse_version(transport.read(3))


def serial_number(transport: Transport) -> str:
    transport.write(build_serial_number())
    return parse_serial_number(transport.read(8))


# ---- ISS_MODE (0x02), datasheet pp.6-10 ----
IO_MODE = 0x00  # p.6
IO_CHANGE = 0x10
I2C_S_20KHZ = 0x20
I2C_S_50KHZ = 0x30
I2C_S_100KHZ = 0x40
I2C_S_400KHZ = 0x50
I2C_H_100KHZ = 0x60
I2C_H_400KHZ = 0x70
I2C_H_1000KHZ = 0x80
SPI_MODE = 0x90  # phase 0-3 in bits 1:0 (p.10)
SERIAL = 0x01  # combinable with IO_MODE (p.8) and the I2C modes (p.9)

I2C_MODES = {
    I2C_S_20KHZ: "I2C_S_20KHZ",
    I2C_S_50KHZ: "I2C_S_50KHZ",
    I2C_S_100KHZ: "I2C_S_100KHZ",
    I2C_S_400KHZ: "I2C_S_400KHZ",
    I2C_H_100KHZ: "I2C_H_100KHZ",
    I2C_H_400KHZ: "I2C_H_400KHZ",
    I2C_H_1000KHZ: "I2C_H_1000KHZ",
}

NACK_REASONS = {0x05: "Unknown command", 0x06: "Internal Error 1", 0x07: "Internal Error 2"}  # p.6

BAUD_MAX_ERROR_PCT = 3.0  # SPEC F2


def decode_mode(b: int) -> str:
    """Name a mode byte as reported by ISS_VERSION. Never raises."""
    if b == IO_MODE:
        return "IO_MODE"
    if b == IO_MODE | SERIAL:
        return "IO_MODE+SERIAL"
    if b == IO_CHANGE:
        return "IO_CHANGE"
    if b in I2C_MODES:
        return I2C_MODES[b]
    if b & ~SERIAL in I2C_MODES:
        return I2C_MODES[b & ~SERIAL] + "+SERIAL"
    if SPI_MODE <= b <= SPI_MODE | 3:
        return f"SPI_MODE phase {b & 3}"
    return f"UNKNOWN(0x{b:02X})"


class IoType(enum.IntEnum):
    """Two-bit pin setting, datasheet p.7."""

    OUTPUT_LOW = 0b00
    OUTPUT_HIGH = 0b01
    DIGITAL_INPUT = 0b10
    ANALOGUE_INPUT = 0b11


def io_type(io1: int, io2: int, io3: int, io4: int) -> int:
    """IO_TYPE byte, datasheet p.7: pin 1 in bits 1:0 ... pin 4 in bits 7:6."""
    out = 0
    for i, pin in enumerate((io1, io2, io3, io4)):
        out |= IoType(pin) << (2 * i)
    return out


def baud_divisor(bps: int) -> tuple[int, float, float]:
    """(divisor, actual_bps, error_pct). SPEC §8: floor(48e6/(16*bps)) - 1, not the p.8 text."""
    if bps <= 0:
        raise ValueError(f"baud rate must be positive, got {bps}")
    divisor = 48_000_000 // (16 * bps) - 1
    actual = 48_000_000 / (16 * (divisor + 1)) if divisor >= 0 else float("inf")
    return divisor, actual, (actual - bps) / bps * 100


def _checked_baud(bps: int) -> int:
    divisor, actual, err = baud_divisor(bps)
    if not 0 <= divisor <= 0xFFFF:
        raise ValueError(f"baud {bps}: divisor {divisor} outside 0-65535")
    if abs(err) > BAUD_MAX_ERROR_PCT:
        raise ValueError(f"baud {bps}: actual {actual:.0f} is {err:+.2f}% off (limit {BAUD_MAX_ERROR_PCT}%)")
    return divisor


SPI_MAX_HZ = 3_000_000
SPI_MIN_HZ = 6_000_000 / 256  # 23437.5, divisor 255


def spi_divisor(sck_hz: float) -> tuple[int, float, float]:
    """(divisor, actual_hz, error_pct), D-005: ceil(6e6/sck) - 1, 1-255; actual never above request."""
    if sck_hz <= 0 or sck_hz > SPI_MAX_HZ or sck_hz < SPI_MIN_HZ:
        raise ValueError(f"SCK {sck_hz} Hz outside {SPI_MIN_HZ}-{SPI_MAX_HZ} Hz")
    divisor = math.ceil(6_000_000 / sck_hz) - 1
    if not 1 <= divisor <= 255:
        raise ValueError(f"SCK {sck_hz} Hz: divisor {divisor} outside 1-255")
    actual = 6_000_000 / (divisor + 1)
    return divisor, actual, (actual - sck_hz) / sck_hz * 100


def _byte(v: int, what: str) -> int:
    if not 0 <= v <= 0xFF:
        raise ValueError(f"{what} {v} is not a byte")
    return v


def _mode_frame(*rest: int) -> bytes:
    return bytes([ISS_CMD, 0x02, *rest])


# IO_MODE, p.7: 5A 02 00 tt
def build_io_mode(io_type: int) -> bytes:
    return _mode_frame(IO_MODE, _byte(io_type, "IO_TYPE"))


# IO_CHANGE, p.7: 5A 02 10 tt
def build_io_change(io_type: int) -> bytes:
    return _mode_frame(IO_CHANGE, _byte(io_type, "IO_TYPE"))


# IO_MODE+SERIAL, p.8: 5A 02 01 hi lo tt
def build_io_serial(bps: int, io_type: int) -> bytes:
    d = _checked_baud(bps)
    return _mode_frame(IO_MODE | SERIAL, d >> 8, d & 0xFF, _byte(io_type, "IO_TYPE"))


def _check_i2c(mode: int) -> int:
    if mode not in I2C_MODES:
        raise ValueError(f"0x{mode:02X} is not an I2C mode")
    return mode


# I2C_MODE, p.9: 5A 02 mm tt
def build_i2c_mode(mode: int, io_type: int) -> bytes:
    return _mode_frame(_check_i2c(mode), _byte(io_type, "IO_TYPE"))


# I2C_MODE+SERIAL, p.9: 5A 02 (mm|01) hi lo
def build_i2c_serial(mode: int, bps: int) -> bytes:
    _check_i2c(mode)
    d = _checked_baud(bps)
    return _mode_frame(mode | SERIAL, d >> 8, d & 0xFF)


# SPI_MODE, p.10: 5A 02 (90|phase) dd
def build_spi_mode(phase: int, sck_hz: float) -> bytes:
    if phase not in range(4):
        raise ValueError(f"SPI phase {phase} outside 0-3")
    return _mode_frame(SPI_MODE | phase, spi_divisor(sck_hz)[0])


def parse_mode_response(resp: bytes) -> None:
    """ISS_MODE response, p.6: FF 00 is OK; 00 rr is NACK with reason rr."""
    if len(resp) < 2:
        raise IssTimeout(f"ISS_MODE: expected 2 bytes, got {len(resp)}")
    first, second = resp[0], resp[1]
    if first == 0xFF:
        if second != 0:
            raise IssProtocolError(f"ISS_MODE: ACK followed by 0x{second:02X}, expected 0x00")
        return
    if first == 0x00:
        if second in NACK_REASONS:
            raise IssNack(second)
        raise IssProtocolError(f"ISS_MODE: NACK with unknown reason 0x{second:02X}")
    raise IssProtocolError(f"ISS_MODE: first byte 0x{first:02X} is neither ACK nor NACK")


def set_mode(transport: Transport, frame: bytes) -> None:
    transport.write(frame)
    parse_mode_response(transport.read(2))


# ---- SERIAL_IO, SETPINS, GETPINS, GETAD, datasheet pp.19-20 ----
SERIAL_IO = 0x62
SETPINS = 0x63
GETPINS = 0x64
GETAD = 0x65
SERIAL_TX_MAX = 30  # p.19: transmit buffer size
SERIAL_RX_MAX = 62  # p.19: receive buffer size
AD_MAX = 1023  # p.20: 10-bit converter


class SerialIoResult(NamedTuple):
    ack: bool
    tx_count: int  # bytes still pending in the transmit buffer (our reading of p.19)
    rx: bytes


# SERIAL_IO, p.19: 62 followed by up to 30 data bytes; no data is the receive poll.
def build_serial_io(data: bytes = b"") -> bytes:
    if len(data) > SERIAL_TX_MAX:
        raise ValueError(f"SERIAL_IO: {len(data)} bytes exceeds the {SERIAL_TX_MAX}-byte transmit buffer")
    return bytes([SERIAL_IO]) + bytes(data)


def parse_serial_io_header(resp: bytes) -> tuple[bool, int, int]:
    """First 3 response bytes, p.19: ACK/NACK, TxCount, RxCount."""
    if len(resp) < 3:
        raise IssTimeout(f"SERIAL_IO: expected 3 header bytes, got {len(resp)}")
    if resp[0] not in (0xFF, 0x00):
        raise IssProtocolError(f"SERIAL_IO: first byte 0x{resp[0]:02X} is neither ACK nor NACK")
    tx_count, rx_count = resp[1], resp[2]
    if tx_count > SERIAL_TX_MAX:
        raise IssProtocolError(f"SERIAL_IO: TxCount {tx_count} > {SERIAL_TX_MAX}")
    if rx_count > SERIAL_RX_MAX:
        raise IssProtocolError(f"SERIAL_IO: RxCount {rx_count} > {SERIAL_RX_MAX}")
    return resp[0] == 0xFF, tx_count, rx_count


def serial_io(transport: Transport, data: bytes = b"") -> SerialIoResult:
    transport.write(build_serial_io(data))
    ack, tx_count, rx_count = parse_serial_io_header(transport.read(3))
    # INTERPRETATION of p.19 (not verified): a NACK only means the transmit buffer had no room,
    # and p.19 says to always read the three header bytes and then RxCount bytes. So a NACK does
    # not raise; the received bytes are still read and returned, or the serial stream would lose them.
    rx = transport.read(rx_count) if rx_count else b""
    if len(rx) < rx_count:
        raise IssTimeout(f"SERIAL_IO: expected {rx_count} rx bytes, got {len(rx)}")
    return SerialIoResult(ack, tx_count, rx)


# SETPINS, p.20: 63 ss, I/O1 in bit 0 ... I/O4 in bit 3; bits 7:4 are X.
def build_set_pins(states: int) -> bytes:
    if not 0 <= states <= 0x0F:
        raise ValueError(f"SETPINS: states 0x{states:X} outside 0x00-0x0F")
    return bytes([SETPINS, states])


def parse_set_pins(resp: bytes) -> None:
    if len(resp) < 1:
        raise IssTimeout("SETPINS: expected 1 byte, got 0")
    if resp[0] == 0xFF:
        return
    if resp[0] == 0x00:
        raise IssNack(None, "SETPINS")
    raise IssProtocolError(f"SETPINS: response 0x{resp[0]:02X} is neither ACK nor NACK")


def set_pins(transport: Transport, states: int) -> None:
    transport.write(build_set_pins(states))
    parse_set_pins(transport.read(1))


# GETPINS, p.20: 64, receive one byte, pin states in bits 3:0.
def build_get_pins() -> bytes:
    return bytes([GETPINS])


def parse_get_pins(resp: bytes) -> int:
    if len(resp) < 1:
        raise IssTimeout("GETPINS: expected 1 byte, got 0")
    return resp[0] & 0x0F  # bits 7:4 are don't-care


def get_pins(transport: Transport) -> int:
    transport.write(build_get_pins())
    return parse_get_pins(transport.read(1))


# GETAD, p.20: 65 cc (channel 1-4), receive 16-bit big-endian value, 10-bit converter.
def build_get_ad(channel: int) -> bytes:
    if not 1 <= channel <= 4:
        raise ValueError(f"GETAD: channel {channel} outside 1-4")
    return bytes([GETAD, channel])


def parse_get_ad(resp: bytes) -> int:
    if len(resp) < 2:
        raise IssTimeout(f"GETAD: expected 2 bytes, got {len(resp)}")
    value = resp[0] << 8 | resp[1]
    if value > AD_MAX:
        raise IssProtocolError(f"GETAD: value {value} exceeds the 10-bit maximum {AD_MAX}")
    return value


def get_ad(transport: Transport, channel: int) -> int:
    transport.write(build_get_ad(channel))
    return parse_get_ad(transport.read(2))


# ---- I2C_SGL, I2C_AD0, I2C_AD1, I2C_AD2, I2C_TEST, datasheet pp.11-16; D-006 ----
I2C_SGL = 0x53
I2C_AD0 = 0x54
I2C_AD1 = 0x55
I2C_AD2 = 0x56
I2C_TEST = 0x58
I2C_AD0_MAX = 60  # D-006: the datasheet gives no limit; same as I2C_AD1
I2C_AD1_MAX = 60  # p.13, reads and writes
I2C_AD2_WRITE_MAX = 59  # p.14: "so as not to overflow the 64 byte internal buffer"
I2C_AD2_READ_MAX = 64  # p.14


def _i2c_addr(addr: int) -> int:
    """Datasheet 8-bit form: the even write address (pp.11-14)."""
    if not 0 <= addr <= 0xFE or addr & 1:
        raise ValueError(f"I2C address 0x{addr:X} is not even and in 0x00-0xFE")
    return addr


def _i2c_count(n: int, limit: int, name: str) -> int:
    if not 1 <= n <= limit:
        raise ValueError(f"{name}: byte count {n} outside 1-{limit}")
    return n


def _i2c_reg(reg: int, top: int, name: str) -> int:
    if not 0 <= reg <= top:
        raise ValueError(f"{name}: register 0x{reg:X} outside 0x00-0x{top:X}")
    return reg


# I2C_SGL, p.11: 53 addr value (write); p.12: 53 addr+1 (read, add 1 to the device address).
def build_i2c_sgl_write(addr: int, value: int) -> bytes:
    return bytes([I2C_SGL, _i2c_addr(addr), _byte(value, "I2C_SGL value")])


def build_i2c_sgl_read(addr: int) -> bytes:
    return bytes([I2C_SGL, _i2c_addr(addr) | 1])


# I2C_AD0, p.12: 54 addr n data... (write); 54 addr+1 n (read).
def build_i2c_ad0_write(addr: int, data: bytes) -> bytes:
    n = _i2c_count(len(data), I2C_AD0_MAX, "I2C_AD0")
    return bytes([I2C_AD0, _i2c_addr(addr), n]) + bytes(data)


def build_i2c_ad0_read(addr: int, n: int) -> bytes:
    return bytes([I2C_AD0, _i2c_addr(addr) | 1, _i2c_count(n, I2C_AD0_MAX, "I2C_AD0")])


# I2C_AD1, p.13: 55 addr reg n data... (write); 55 addr+1 reg n (read).
def build_i2c_ad1_write(addr: int, reg: int, data: bytes) -> bytes:
    n = _i2c_count(len(data), I2C_AD1_MAX, "I2C_AD1")
    return bytes([I2C_AD1, _i2c_addr(addr), _i2c_reg(reg, 0xFF, "I2C_AD1"), n]) + bytes(data)


def build_i2c_ad1_read(addr: int, reg: int, n: int) -> bytes:
    return bytes([I2C_AD1, _i2c_addr(addr) | 1, _i2c_reg(reg, 0xFF, "I2C_AD1"),
                  _i2c_count(n, I2C_AD1_MAX, "I2C_AD1")])


# I2C_AD2, p.14: 56 addr regH regL n data... (write); 56 addr+1 regH regL n (read). High byte first.
def build_i2c_ad2_write(addr: int, reg: int, data: bytes) -> bytes:
    n = _i2c_count(len(data), I2C_AD2_WRITE_MAX, "I2C_AD2 write")
    _i2c_reg(reg, 0xFFFF, "I2C_AD2")
    return bytes([I2C_AD2, _i2c_addr(addr), reg >> 8, reg & 0xFF, n]) + bytes(data)


def build_i2c_ad2_read(addr: int, reg: int, n: int) -> bytes:
    _i2c_reg(reg, 0xFFFF, "I2C_AD2")
    return bytes([I2C_AD2, _i2c_addr(addr) | 1, reg >> 8, reg & 0xFF,
                  _i2c_count(n, I2C_AD2_READ_MAX, "I2C_AD2 read")])


# I2C_TEST, p.16: 58 addr; reply 00 if the device is absent, non-zero if it is present.
def build_i2c_test(addr: int) -> bytes:
    return bytes([I2C_TEST, _i2c_addr(addr)])


def parse_i2c_write(resp: bytes, command: str) -> None:
    """Every I2C write, pp.11-14: 00 if the write failed, non-zero if it succeeded."""
    if len(resp) < 1:
        raise IssTimeout(f"{command}: expected 1 byte, got 0")
    if resp[0] == 0x00:
        raise IssNack(None, command)


def parse_i2c_read(resp: bytes, n: int) -> bytes:
    # The datasheet defines no status byte for reads, so a read from an absent device
    # can't be detected from the response.
    if len(resp) < n:
        raise IssTimeout(f"I2C read: expected {n} bytes, got {len(resp)}")
    return bytes(resp[:n])


def parse_i2c_test(resp: bytes) -> bool:
    if len(resp) < 1:
        raise IssTimeout("I2C_TEST: expected 1 byte, got 0")
    return resp[0] != 0x00


def _i2c_write(transport: Transport, frame: bytes, command: str) -> None:
    transport.write(frame)
    parse_i2c_write(transport.read(1), command)


def _i2c_read(transport: Transport, frame: bytes, n: int) -> bytes:
    transport.write(frame)
    return parse_i2c_read(transport.read(n), n)


def i2c_sgl_write(transport: Transport, addr: int, value: int) -> None:
    _i2c_write(transport, build_i2c_sgl_write(addr, value), "I2C_SGL")


def i2c_sgl_read(transport: Transport, addr: int) -> int:
    return _i2c_read(transport, build_i2c_sgl_read(addr), 1)[0]


def i2c_ad0_write(transport: Transport, addr: int, data: bytes) -> None:
    _i2c_write(transport, build_i2c_ad0_write(addr, data), "I2C_AD0")


def i2c_ad0_read(transport: Transport, addr: int, n: int) -> bytes:
    return _i2c_read(transport, build_i2c_ad0_read(addr, n), n)


def i2c_ad1_write(transport: Transport, addr: int, reg: int, data: bytes) -> None:
    _i2c_write(transport, build_i2c_ad1_write(addr, reg, data), "I2C_AD1")


def i2c_ad1_read(transport: Transport, addr: int, reg: int, n: int) -> bytes:
    return _i2c_read(transport, build_i2c_ad1_read(addr, reg, n), n)


def i2c_ad2_write(transport: Transport, addr: int, reg: int, data: bytes) -> None:
    _i2c_write(transport, build_i2c_ad2_write(addr, reg, data), "I2C_AD2")


def i2c_ad2_read(transport: Transport, addr: int, reg: int, n: int) -> bytes:
    return _i2c_read(transport, build_i2c_ad2_read(addr, reg, n), n)


def i2c_test(transport: Transport, addr: int) -> bool:
    transport.write(build_i2c_test(addr))
    return parse_i2c_test(transport.read(1))


# ---- I2C_DIRECT, datasheet pp.15-16; D-007 ----
I2C_DIRECT = 0x57  # p.15
I2C_DIRECT_START = 0x01  # p.15
I2C_DIRECT_RESTART = 0x02  # p.15
I2C_DIRECT_STOP = 0x03  # p.15
I2C_DIRECT_NACK = 0x04  # p.15: send NACK after the next read
I2C_DIRECT_READ_BASE = 0x20  # p.15: READ 0x20-0x2F reads 1-16 bytes
I2C_DIRECT_WRITE_BASE = 0x30  # p.15: WRITE 0x30-0x3F writes the next 1-16 bytes
I2C_DIRECT_FRAME_MAX = 59  # D-007: the whole frame, 0x57 included (p.15: "< 60 bytes")
I2C_DIRECT_CHUNK_MAX = 16  # p.15: bytes per READ or WRITE sub-command
I2C_DIRECT_READ_TOTAL_MAX = 60  # D-007: the datasheet gives no limit; closest documented read limit (p.13)
I2C_DIRECT_NACK_REASONS = {0x01: "Device Error", 0x02: "Buffer Overflow", 0x03: "Buffer Underflow", 0x04: "Unknown command"}  # p.15


# READ, p.15: one sub-command byte, 0x20 + n - 1.
def direct_read(n: int) -> bytes:
    if not 1 <= n <= I2C_DIRECT_CHUNK_MAX:
        raise ValueError(f"I2C_DIRECT READ: byte count {n} outside 1-{I2C_DIRECT_CHUNK_MAX}")
    return bytes([I2C_DIRECT_READ_BASE + n - 1])


# WRITE, p.15: sub-command byte 0x30 + n - 1, then the n bytes. The device address is written like any other byte.
def direct_write(data: bytes) -> bytes:
    if not 1 <= len(data) <= I2C_DIRECT_CHUNK_MAX:
        raise ValueError(f"I2C_DIRECT WRITE: byte count {len(data)} outside 1-{I2C_DIRECT_CHUNK_MAX}")
    return bytes([I2C_DIRECT_WRITE_BASE + len(data) - 1]) + bytes(data)


def _direct_walk(frame: bytes) -> tuple[int, int]:
    """Walk the sub-commands after the 0x57 byte. Returns (sub-command count, total READ bytes)."""
    subs = reads = 0
    i = 1
    while i < len(frame):
        sub = frame[i]
        subs += 1
        i += 1
        if I2C_DIRECT_START <= sub <= I2C_DIRECT_NACK:
            continue
        if 0x20 <= sub <= 0x2F:
            reads += sub - I2C_DIRECT_READ_BASE + 1
        elif 0x30 <= sub <= 0x3F:
            k = sub - I2C_DIRECT_WRITE_BASE + 1
            if len(frame) - i < k:
                raise ValueError(f"I2C_DIRECT: WRITE 0x{sub:02X} needs {k} data bytes, only {len(frame) - i} follow")
            i += k
        else:
            raise ValueError(f"I2C_DIRECT: 0x{sub:02X} is not a sub-command")
    return subs, reads


# I2C_DIRECT, p.15: 57 followed by sub-commands. Checks the frame structure and D-007's limits, not I2C semantics.
def build_i2c_direct(*parts: int | bytes) -> bytes:
    frame = bytearray([I2C_DIRECT])
    for part in parts:
        if isinstance(part, int):
            frame.append(_byte(part, "I2C_DIRECT sub-command"))
        else:
            frame += part
    frame = bytes(frame)
    subs, reads = _direct_walk(frame)
    if subs == 0:
        raise ValueError("I2C_DIRECT: no sub-commands")
    if len(frame) > I2C_DIRECT_FRAME_MAX:
        raise ValueError(f"I2C_DIRECT: frame of {len(frame)} bytes exceeds {I2C_DIRECT_FRAME_MAX}")
    if reads > I2C_DIRECT_READ_TOTAL_MAX:
        raise ValueError(f"I2C_DIRECT: {reads} bytes read exceeds {I2C_DIRECT_READ_TOTAL_MAX}")
    return frame


def i2c_direct_read_count(frame: bytes) -> int:
    """Total bytes the READ sub-commands of a built frame will return."""
    return _direct_walk(frame)[1]


def parse_i2c_direct_status(resp: bytes) -> int:
    """I2C_DIRECT status bytes, p.15: FF nn is ACK with nn bytes to read; 00 rr is NACK with reason rr."""
    if len(resp) < 2:
        raise IssTimeout(f"I2C_DIRECT: expected 2 status bytes, got {len(resp)}")
    if resp[0] == 0xFF:
        return resp[1]
    if resp[0] == 0x00:
        raise IssNack(resp[1], "I2C_DIRECT")
    raise IssProtocolError(f"I2C_DIRECT: first byte 0x{resp[0]:02X} is neither ACK nor NACK")


def i2c_direct(transport: Transport, *parts: int | bytes) -> bytes:
    frame = build_i2c_direct(*parts)
    transport.write(frame)  # one write(): the device ends a frame at an inter-byte gap (D-007)
    n = parse_i2c_direct_status(transport.read(2))
    data = transport.read(n) if n else b""
    if len(data) < n:
        raise IssTimeout(f"I2C_DIRECT: expected {n} data bytes, got {len(data)}")
    expected = i2c_direct_read_count(frame)
    if n != expected:
        raise IssProtocolError(f"I2C_DIRECT: device reports {n} bytes, frame reads {expected}")
    return bytes(data)
